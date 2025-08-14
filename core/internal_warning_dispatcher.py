# core/internal_warning_dispatcher.py
# HAIL — InternalWarningDispatcher (Upgraded, backward compatible)
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Dict, List, Optional
import json
import re

# Optional sinks (best‑effort; do not hard‑depend)
try:
    from core.founder_alert import FounderAlert  # type: ignore
except Exception:  # pragma: no cover
    FounderAlert = None  # type: ignore

try:
    from core.deen_emergency_mode import DeenEmergencyMode  # type: ignore
except Exception:  # pragma: no cover
    DeenEmergencyMode = None  # type: ignore

try:
    from core.action_logger import ActionLogger  # type: ignore
except Exception:  # pragma: no cover
    ActionLogger = None  # type: ignore


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class WarningEvent:
    ts: datetime
    source: str
    message: str
    level: str = "medium"   # low | medium | high | critical
    status: str = "active"  # active | cleared | escalated
    dedupe_key: str = ""    # normalized signature

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ts"] = self.ts.isoformat()
        return d


class InternalWarningDispatcher:
    """
    Central warning dispatcher with throttling, dedupe, and escalation.
    Backward‑compatible API:
      - dispatch_warning(source, message, level="medium") -> {status, warning}
      - trigger_emergency_protocol(warning)
      - get_all_warnings()
      - clear_warnings()
    New:
      - configure(rate_limit=timedelta, window=timedelta)
      - mute_source(source)/unmute_source(source)
      - recent(n), export_json(), stats()
    """

    # default throttle per (source, dedupe_key)
    DEFAULT_RATE_LIMIT = timedelta(seconds=30)
    DEFAULT_WINDOW = timedelta(hours=2)

    def __init__(
        self,
        *,
        rate_limit: timedelta = DEFAULT_RATE_LIMIT,
        window: timedelta = DEFAULT_WINDOW,
        mission_log_sink: Optional[callable] = None,   # lambda payload: mission_log.append(...)
    ):
        self._lock = RLock()
        self.warning_log: List[dict] = []  # keep legacy public name (list[dict])
        self._events: List[WarningEvent] = []
        self._last_seen: Dict[tuple, datetime] = {}  # (source, key) -> ts
        self._rate_limit = rate_limit
        self._window = window
        self._muted: Dict[str, bool] = {}

        # Sinks
        self._alert = FounderAlert() if FounderAlert else None
        self._emergency = DeenEmergencyMode() if DeenEmergencyMode else None
        self._action_logger = ActionLogger() if ActionLogger else None
        self._mission_log_sink = mission_log_sink

    # ------------- Backward‑compatible methods -------------

    def dispatch_warning(self, source: str, message: str, level: str = "medium"):
        src = (source or "unknown").strip()
        msg = message.strip()
        lvl = (level or "medium").lower()
        lvl = lvl if lvl in {"low", "medium", "high", "critical"} else "medium"

        if self._muted.get(src, False):
            return {"status": "muted", "warning": {"source": src, "message": msg, "level": lvl}}

        ev = WarningEvent(
            ts=_utcnow(),
            source=src,
            message=msg,
            level=lvl,
            status="active",
            dedupe_key=self._make_key(src, msg, lvl),
        )

        # Throttle repeated identical warnings per source
        with self._lock:
            if self._is_throttled(ev):
                return {"status": "throttled", "warning": ev.to_dict()}

            self._record(ev)

        # Escalation
        if lvl in {"high", "critical"}:
            self.trigger_emergency_protocol(ev.to_dict())

        # Sinks
        self._sink_action("WarningDispatch", f"{src} :: {lvl} :: {msg[:160]}")
        self._sink_mission(ev, escalated=(lvl in {"high", "critical"}))

        return {"status": "dispatched", "warning": ev.to_dict()}

    def trigger_emergency_protocol(self, warning):
        """
        Backward‑compatible entry; accepts dict (from ev.to_dict()).
        """
        src = warning.get("source", "unknown")
        msg = warning.get("message", "")
        lvl = warning.get("level", "medium")

        # Console fallback (original behavior)
        print(f"🚨 EMERGENCY WARNING: {msg} (Source: {src})")

        # Founder email (best‑effort)
        if self._alert and lvl in {"high", "critical"}:
            try:
                self._alert.send_alert(
                    subject=f"{lvl.upper()} from {src}",
                    message_body=msg,
                )
            except Exception:
                pass

        # Tighten system if available
        if self._emergency and lvl == "critical":
            try:
                self._emergency.activate(reason=f"{src}: {msg}")
            except Exception:
                pass

    def get_all_warnings(self):
        # Legacy: return the simple dict list
        with self._lock:
            return list(self.warning_log)

    def clear_warnings(self):
        with self._lock:
            self._events.clear()
            self.warning_log.clear()
            self._last_seen.clear()
        return "✅ All internal warnings cleared."

    # ------------- New helpers -------------

    def configure(self, *, rate_limit: Optional[timedelta] = None, window: Optional[timedelta] = None):
        with self._lock:
            if rate_limit is not None:
                self._rate_limit = rate_limit
            if window is not None:
                self._window = window

    def mute_source(self, source: str):
        with self._lock:
            self._muted[source] = True
        return f"🔇 Source muted: {source}"

    def unmute_source(self, source: str):
        with self._lock:
            self._muted[source] = False
        return f"🔊 Source unmuted: {source}"

    def recent(self, n: int = 50) -> List[dict]:
        with self._lock:
            return [e.to_dict() for e in self._events[-int(n):]]

    def export_json(self) -> str:
        return json.dumps(self.recent(1000), ensure_ascii=False, indent=2)

    def stats(self) -> dict:
        with self._lock:
            total = len(self._events)
            by_level: Dict[str, int] = {"low": 0, "medium": 0, "high": 0, "critical": 0}
            for e in self._events:
                by_level[e.level] = by_level.get(e.level, 0) + 1
            return {"total": total, "by_level": by_level, "muted_sources": [k for k, v in self._muted.items() if v]}

    # ------------- Internals -------------

    @staticmethod
    def _make_key(source: str, message: str, level: str) -> str:
        s = f"{source}|{level}|{message}"
        # normalize whitespace and numbers to reduce duplicates
        s = re.sub(r"\s+", " ", s)
        s = re.sub(r"\d+", "<n>", s)
        return s.strip().lower()

    def _is_throttled(self, ev: WarningEvent) -> bool:
        now = ev.ts
        key = (ev.source, ev.dedupe_key)
        last = self._last_seen.get(key)
        if last and (now - last) < self._rate_limit:
            return True
        # purge old window entries to keep map small
        for k, ts in list(self._last_seen.items()):
            if now - ts > self._window:
                self._last_seen.pop(k, None)
        self._last_seen[key] = now
        return False

    def _record(self, ev: WarningEvent) -> None:
        self._events.append(ev)
        # legacy mirror
        self.warning_log.append({
            "source": ev.source,
            "message": ev.message,
            "level": ev.level,
            "status": ev.status,
            "timestamp": ev.ts.isoformat(),
        })

    # ------------- Sinks -------------

    def _sink_action(self, action: str, reason: str) -> None:
        if not self._action_logger:
            return
        try:
            self._action_logger.log(
                action_type=action,
                user_input="internal_warning",
                system_decision="OK",
                module="internal_warning_dispatcher",
                reason=reason[:300],
                status="Success",
            )
        except Exception:
            pass

    def _sink_mission(self, ev: WarningEvent, *, escalated: bool) -> None:
        if not callable(self._mission_log_sink):
            return
        try:
            verdict = "shubha" if ev.level in {"low", "medium"} else "haram"
            score = 0.35 if ev.level in {"low", "medium"} else 0.75
            if escalated and ev.level == "critical":
                score = 0.9
            self._mission_log_sink({
                "actor_id": f"system:{ev.source}",
                "activity": "internal_warning",
                "verdict": verdict,
                "score": score,
                "reasons": [f"level={ev.level}", ev.message[:120]],
                "tags": ["warning", "internal", ev.level],
                "payload": ev.to_dict(),
            })
        except Exception:
            pass
