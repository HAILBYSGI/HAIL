# core/deen_violation_logger.py
# HAIL — DeenViolationLogger (Upgraded)
from __future__ import annotations

import json
import os
import tempfile
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Optional


@dataclass
class ViolationEntry:
    timestamp: str
    module: str
    action: str
    reason: str
    level: str = "critical"   # "info" | "low" | "medium" | "high" | "critical"
    meta: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if d["meta"] is None:
            d.pop("meta")
        return d


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DeenViolationLogger:
    """
    Append-only violation log with atomic persistence + rotation.

    Public API (backwards compatible):
      - log_violation(module, action, reason, level="critical")
      - get_recent_violations(count=10)

    Extras:
      - export_json(), tail(n), find_by_module(), count_by_level(), clear()
      - thread-safe via RLock
      - atomic writes; rotates when file grows beyond max_size_bytes
    """

    def __init__(
        self,
        log_file: str = "hail/logs/deen_violations.json",
        *,
        max_size_bytes: int = 2_000_000,  # ~2MB
        keep_backups: int = 5,
    ) -> None:
        self._path = Path(log_file)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._max_size = int(max_size_bytes)
        self._keep_backups = int(keep_backups)
        self._lock = RLock()
        self._entries: List[ViolationEntry] = []

        # Load existing file if present
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                for obj in data:
                    self._entries.append(
                        ViolationEntry(
                            timestamp=str(obj.get("timestamp", _utc_iso())),
                            module=str(obj.get("module", "unknown")),
                            action=str(obj.get("action", "")),
                            reason=str(obj.get("reason", "")),
                            level=str(obj.get("level", "critical")),
                            meta=obj.get("meta"),
                        )
                    )
            except Exception:
                # start fresh if corrupt
                self._entries = []
                self._atomic_write([])  # ensure file exists
        else:
            self._atomic_write([])

        # Optional action logger sink
        try:
            from core.action_logger import ActionLogger  # type: ignore
            self._action_logger = ActionLogger()
        except Exception:
            self._action_logger = None

        # Optional mission log sink
        self._mission_log_sink = None  # set with set_mission_log_sink(callable)

    # ----------------- Public (backward compatible) -----------------

    def log_violation(self, module: str, action: str, reason: str, level: str = "critical", *, meta: Optional[Dict[str, Any]] = None) -> None:
        entry = ViolationEntry(
            timestamp=_utc_iso(),
            module=module,
            action=action,
            reason=reason,
            level=level,
            meta=meta,
        )
        with self._lock:
            self._entries.append(entry)
            self._persist_unlocked()

        # Sink: ActionLogger
        if self._action_logger:
            try:
                self._action_logger.log(
                    action_type="DeenViolation",
                    user_input=action,
                    system_decision="DENIED",
                    module=module,
                    reason=reason[:300],
                    status=level.upper(),
                )
            except Exception:
                pass

        # Sink: Mission Log
        if self._mission_log_sink:
            try:
                self._mission_log_sink({
                    "actor_id": meta.get("actor_id") if isinstance(meta, dict) else "user",
                    "activity": "deen_violation",
                    "verdict": "haram",
                    "score": 0.9,
                    "reasons": [reason[:120]],
                    "tags": ["violation", level],
                    "payload": entry.to_dict(),
                })
            except Exception:
                pass

        print(f"🚨 Deen violation recorded: {entry.to_dict()}")

    def get_recent_violations(self, count: int = 10) -> List[Dict[str, Any]]:
        with self._lock:
            return [e.to_dict() for e in self._entries[-int(count):]]

    # ----------------- Extra helpers (safe to use) -----------------

    def export_json(self) -> str:
        with self._lock:
            return json.dumps([e.to_dict() for e in self._entries], ensure_ascii=False, indent=2)

    def tail(self, n: int = 50) -> List[Dict[str, Any]]:
        return self.get_recent_violations(n)

    def find_by_module(self, module: str, limit: int = 100) -> List[Dict[str, Any]]:
        m = (module or "").strip().lower()
        with self._lock:
            out = [e.to_dict() for e in reversed(self._entries) if e.module.lower() == m]
            return list(reversed(out[:limit]))

    def count_by_level(self) -> Dict[str, int]:
        with self._lock:
            agg: Dict[str, int] = {}
            for e in self._entries:
                agg[e.level] = agg.get(e.level, 0) + 1
            return agg

    def clear(self) -> None:
        with self._lock:
            self._entries = []
            self._atomic_write([])

    def set_mission_log_sink(self, fn) -> None:
        """Provide a function(payload: dict) -> None to mirror violations into the mission log."""
        self._mission_log_sink = fn

    # ----------------- Persistence internals -----------------

    def _persist_unlocked(self) -> None:
        # rotate if large
        try:
            if self._path.exists() and self._path.stat().st_size > self._max_size:
                self._rotate_unlocked()
        except Exception:
            pass
        self._atomic_write([e.to_dict() for e in self._entries])

    def _atomic_write(self, data: List[Dict[str, Any]]) -> None:
        tmp_fd, tmp_path = tempfile.mkstemp(prefix="violations_", suffix=".json", dir=str(self._path.parent))
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as tmp:
                json.dump(data, tmp, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self._path)
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass

    def _rotate_unlocked(self) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        backup = self._path.parent / f"deen_violations.{ts}.json"
        try:
            shutil.copy2(self._path, backup)
            backups = sorted(self._path.parent.glob("deen_violations.*.json"), reverse=True)
            for old in backups[self._keep_backups:]:
                try:
                    old.unlink()
                except OSError:
                    pass
        except Exception:
            pass


# ---------------- Quick self-test ----------------
if __name__ == "__main__":
    dv = DeenViolationLogger(log_file=None if False else "hail/logs/deen_violations.json")  # default
    dv.log_violation("guardian", "opened haram link", "Matched deny: riba, nudity", level="high", meta={"actor_id": "husnain_ali"})
    dv.log_violation("monitor", "spam attempts", "Surge detected by EWMA", level="medium")
    print(dv.get_recent_violations(2))
    print(dv.count_by_level())
    print(dv.export_json())
