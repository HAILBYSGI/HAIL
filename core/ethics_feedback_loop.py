# core/ethics_feedback_loop.py
# HAIL — EthicsFeedbackLoop (Upgraded)
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Dict, List, Optional

# Optional sink (best-effort)
try:
    from core.action_logger import ActionLogger  # type: ignore
except Exception:  # pragma: no cover
    ActionLogger = None  # type: ignore


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="ethics_", suffix=".json", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as w:
            json.dump(data, w, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


@dataclass
class FeedbackEntry:
    source: str
    message: str
    severity: str = "medium"      # "low" | "medium" | "high" | "critical"
    status: str = "pending_review"  # "pending_review" | "resolved" | "rejected"
    created_at: str = field(default_factory=_utc_iso)
    updated_at: str = field(default_factory=_utc_iso)
    decision: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EthicsFeedbackLoop:
    """
    Collects and reviews ethics feedback from authorized sources.
    Features:
      - Source allowlist (founder, shariah_board, users optional)
      - Severity validation
      - Thread-safe in-memory log
      - Atomic JSON persistence
      - Optional sinks: ActionLogger + Mission Log
    """

    VALID_SEVERITIES = {"low", "medium", "high", "critical"}
    VALID_STATUSES = {"pending_review", "resolved", "rejected"}

    def __init__(
        self,
        *,
        storage_path: str = "hail/logs/ethics_feedback.json",
        enable_users: bool = False,
        mission_log_sink: Optional[callable] = None,  # lambda payload: mission_log.append(...)
    ) -> None:
        self._storage_path = storage_path
        self._lock = RLock()
        self._entries: List[FeedbackEntry] = []
        self._sources: Dict[str, bool] = {
            "founder": True,
            "shariah_board": True,
            "users": bool(enable_users),
        }
        self._mission_log_sink = mission_log_sink
        self._action_logger = ActionLogger() if ActionLogger else None

        # Load existing file if present
        self._load()

    # ---------------- Public API ----------------

    def record_feedback(self, source: str, message: str, severity: str = "medium", *, meta: Optional[Dict[str, Any]] = None) -> str:
        if source not in self._sources or not self._sources[source]:
            return f"Feedback source '{source}' not authorized or disabled."

        sev = (severity or "medium").lower().strip()
        if sev not in self.VALID_SEVERITIES:
            sev = "medium"

        entry = FeedbackEntry(source=source, message=message.strip(), severity=sev, meta=meta or {})

        with self._lock:
            self._entries.append(entry)
            self._persist()

        # sinks
        self._sink_action("FeedbackRecorded", entry)
        self._sink_mission("feedback_recorded", entry, verdict="halal", score=0.06)

        return "✅ Feedback recorded for review."

    def review_feedback(self) -> List[Dict[str, Any]]:
        with self._lock:
            pending = [e.to_dict() for e in self._entries if e.status == "pending_review"]
        return pending if pending else [{"message": "✅ No pending feedback."}]

    def resolve_feedback(self, index: int, decision: str) -> str:
        with self._lock:
            if not (0 <= index < len(self._entries)):
                return "⚠️ Invalid feedback index."
            e = self._entries[index]
            e.status = "resolved"
            e.decision = (decision or "").strip() or "accepted"
            e.updated_at = _utc_iso()
            self._persist()
            self._sink_action("FeedbackResolved", e, extra={"index": index})
            self._sink_mission("feedback_resolved", e, verdict="halal", score=0.05)
        return f"✅ Feedback #{index} resolved."

    def reject_feedback(self, index: int, reason: str = "") -> str:
        with self._lock:
            if not (0 <= index < len(self._entries)):
                return "⚠️ Invalid feedback index."
            e = self._entries[index]
            e.status = "rejected"
            e.decision = (reason or "rejected")
            e.updated_at = _utc_iso()
            self._persist()
            self._sink_action("FeedbackRejected", e, extra={"index": index})
            self._sink_mission("feedback_rejected", e, verdict="shubha", score=0.2)
        return f"✅ Feedback #{index} rejected."

    def enable_feedback_source(self, source: str) -> str:
        with self._lock:
            self._sources[source] = True
        return f"✅ Feedback from '{source}' enabled."

    def disable_feedback_source(self, source: str) -> str:
        with self._lock:
            self._sources[source] = False
        return f"✅ Feedback from '{source}' disabled."

    # -------- Convenience / Queries --------

    def list_all(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [e.to_dict() for e in self._entries]

    def counts(self) -> Dict[str, Any]:
        with self._lock:
            by_status: Dict[str, int] = {}
            by_severity: Dict[str, int] = {}
            for e in self._entries:
                by_status[e.status] = by_status.get(e.status, 0) + 1
                by_severity[e.severity] = by_severity.get(e.severity, 0) + 1
            return {"status": by_status, "severity": by_severity, "total": len(self._entries)}

    def filter_by_source(self, source: str) -> List[Dict[str, Any]]:
        s = (source or "").strip().lower()
        with self._lock:
            return [e.to_dict() for e in self._entries if e.source.lower() == s]

    def export_json(self) -> str:
        with self._lock:
            return json.dumps([e.to_dict() for e in self._entries], ensure_ascii=False, indent=2)

    # ---------------- Internals ----------------

    def _load(self) -> None:
        try:
            if os.path.exists(self._storage_path):
                data = json.loads(open(self._storage_path, "r", encoding="utf-8").read())
                with self._lock:
                    self._entries = [
                        FeedbackEntry(
                            source=obj.get("source", "unknown"),
                            message=obj.get("message", ""),
                            severity=obj.get("severity", "medium"),
                            status=obj.get("status", "pending_review"),
                            created_at=obj.get("created_at", _utc_iso()),
                            updated_at=obj.get("updated_at", _utc_iso()),
                            decision=obj.get("decision"),
                            meta=obj.get("meta") or {},
                        )
                        for obj in data or []
                    ]
        except Exception:
            # If corrupt, start fresh but preserve the damaged file as .broken
            try:
                os.replace(self._storage_path, self._storage_path + ".broken")
            except Exception:
                pass
            with self._lock:
                self._entries = []
                _atomic_write_json(self._storage_path, [])

    def _persist(self) -> None:
        _atomic_write_json(self._storage_path, [e.to_dict() for e in self._entries])

    # --------------- Sinks ---------------

    def _sink_action(self, action_type: str, entry: FeedbackEntry, *, extra: Optional[Dict[str, Any]] = None) -> None:
        if not self._action_logger:
            return
        try:
            self._action_logger.log(
                action_type=action_type,
                user_input=entry.message[:160],
                system_decision=entry.status.upper(),
                module="ethics_feedback_loop",
                reason=f"source={entry.source} severity={entry.severity}",
                status="Success",
            )
        except Exception:
            pass

    def _sink_mission(self, activity: str, entry: FeedbackEntry, *, verdict: str, score: float) -> None:
        if not self._mission_log_sink:
            return
        try:
            self._mission_log_sink({
                "actor_id": f"feedback:{entry.source}",
                "activity": activity,
                "verdict": verdict,
                "score": float(score),
                "reasons": [f"severity={entry.severity}", f"status={entry.status}"],
                "tags": ["ethics", "feedback", entry.severity],
                "payload": entry.to_dict(),
            })
        except Exception:
            pass


# ---------------- Minimal self-test ----------------
if __name__ == "__main__":
    efl = EthicsFeedbackLoop(enable_users=True)
    print(efl.record_feedback("founder", "Tighten rules around idle scrolling.", "high"))
    print(efl.record_feedback("users", "Dark mode toggle?", "low"))
    print(efl.review_feedback())
    print(efl.resolve_feedback(0, "Accepted; will implement."))
    print(efl.reject_feedback(1, "Not in scope for core ethics."))
    print(efl.counts())
    print(efl.export_json())
