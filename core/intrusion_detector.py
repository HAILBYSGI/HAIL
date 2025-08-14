# core/intrusion_detector.py
# HAIL — IntrusionDetector (Upgraded, backward compatible)
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import List, Dict, Optional
import json
import re

# Optional sinks (best‑effort; do not hard‑depend)
try:
    from core.action_logger import ActionLogger  # type: ignore
except Exception:  # pragma: no cover
    ActionLogger = None  # type: ignore

try:
    from core.founder_alert import FounderAlert  # type: ignore
except Exception:  # pragma: no cover
    FounderAlert = None  # type: ignore

try:
    from core.deen_emergency_mode import DeenEmergencyMode  # type: ignore
except Exception:  # pragma: no cover
    DeenEmergencyMode = None  # type: ignore

try:
    from core.deen_activity_monitor import (  # type: ignore
        DeenActivityMonitor, ActivityEvent, ActivityType
    )
except Exception:  # pragma: no cover
    DeenActivityMonitor = None  # type: ignore
    ActivityEvent = None  # type: ignore
    ActivityType = None  # type: ignore


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class IntrusionEvent:
    ts: datetime
    type: str
    detail: str
    level: str = "notice"  # notice|warning|high|critical
    actor: str = "unknown"

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["ts"] = self.ts.isoformat()
        return d


class IntrusionDetector:
    """
    Backward‑compatible intrusion detection with escalation.
    Preserved methods:
      - log_alert(alert_type, detail)
      - detect_failed_verification(user_id=None)
      - detect_suspicious_input(query_text)
      - trigger_lockdown(reason)
      - reset_alerts()

    New:
      - status(), recent(n), export_json(), configure(...)
      - Cooldown & dedupe for noisy alerts
      - Optional sinks: FounderAlert, DeenEmergencyMode, ActionLogger, DeenActivityMonitor
    """

    # Policy defaults
    MAX_FAILURES = 3                       # lockdown after this many failed verifications
    COOLDOWN = timedelta(seconds=20)       # cooldown per (type, detail)
    WINDOW = timedelta(minutes=15)         # retention window for dedupe map

    # Suspicious keywords (extend as needed)
    SUSPICIOUS = (
        "bypass", "hack", "shutdown", "disable", "kill switch", "root access",
        "override sharia", "backdoor", "token leak", "exfiltrate", "drop table"
    )

    def __init__(
        self,
        *,
        max_failures: int = MAX_FAILURES,
        cooldown: timedelta = COOLDOWN,
        window: timedelta = WINDOW,
        mission_log_sink: Optional[callable] = None,   # lambda payload: mission_log.append(...)
        activity_monitor: Optional[object] = None,     # pass DeenActivityMonitor() if available
    ) -> None:
        self._lock = RLock()
        self._events: List[IntrusionEvent] = []
        self.failed_verifications = 0
        self.suspicious_queries: List[str] = []
        self.lockdown_triggered = False
        self.max_failures = int(max_failures)
        self._cooldown = cooldown
        self._window = window
        self._last_seen: Dict[tuple, datetime] = {}  # (type, detail_norm) -> ts

        # Sinks
        self._action_logger = ActionLogger() if ActionLogger else None
        self._founder_alert = FounderAlert() if FounderAlert else None
        self._emergency = DeenEmergencyMode() if DeenEmergencyMode else None
        self._mission_log_sink = mission_log_sink
        self._monitor = activity_monitor if activity_monitor is not None else (DeenActivityMonitor() if DeenActivityMonitor else None)

        # Backward‑compat mirrors
        self.alert_log: List[Dict] = []  # list of dict entries like before

    # ---------------- Backward‑compatible API ----------------

    def log_alert(self, alert_type, detail):
        """
        Records an intrusion alert (keeps original print behavior via sinks).
        """
        self._emit_event(alert_type, str(detail), level=self._level_from_type(alert_type))
        # Original behavior printed to console; we keep that effect via ActionLogger / sinks.
        # If you still want a print: uncomment below
        # print(f"[INTRUSION ALERT] {alert_type} at {_utcnow().isoformat()}: {detail}")

    def detect_failed_verification(self, user_id=None):
        with self._lock:
            self.failed_verifications += 1
            count = self.failed_verifications
        self._emit_event(
            "Failed Verification",
            f"Attempt #{count} by {user_id or 'unknown'}",
            level="warning",
            actor=user_id or "unknown",
        )
        if count >= self.max_failures and not self.lockdown_triggered:
            self.trigger_lockdown("Multiple failed verification attempts.")

    def detect_suspicious_input(self, query_text):
        text = (query_text or "")
        if any(kw in text.lower() for kw in self.SUSPICIOUS):
            with self._lock:
                self.suspicious_queries.append(text)
            self._emit_event("Suspicious Input", text, level="high")

    def trigger_lockdown(self, reason):
        with self._lock:
            self.lockdown_triggered = True
        self._emit_event("LOCKDOWN INITIATED", str(reason), level="critical")
        # Escalation path
        if self._founder_alert:
            try:
                self._founder_alert.send_alert("LOCKDOWN INITIATED", reason)
            except Exception:
                pass
        if self._emergency:
            try:
                self._emergency.activate(reason=reason)
            except Exception:
                pass

    def reset_alerts(self):
        with self._lock:
            self._events.clear()
            self.alert_log = []
            self.failed_verifications = 0
            self.suspicious_queries = []
            self.lockdown_triggered = False

    # ---------------- New helpers ----------------

    def status(self) -> Dict[str, object]:
        with self._lock:
            return {
                "failed_verifications": self.failed_verifications,
                "suspicious_count": len(self.suspicious_queries),
                "lockdown_triggered": self.lockdown_triggered,
                "recent_events": len(self._events)
            }

    def recent(self, n: int = 50) -> List[Dict]:
        with self._lock:
            return [e.to_dict() for e in self._events[-int(n):]]

    def export_json(self) -> str:
        return json.dumps(self.recent(1000), ensure_ascii=False, indent=2)

    def configure(self, *, max_failures: Optional[int] = None, cooldown: Optional[timedelta] = None, window: Optional[timedelta] = None):
        with self._lock:
            if max_failures is not None:
                self.max_failures = int(max_failures)
            if cooldown is not None:
                self._cooldown = cooldown
            if window is not None:
                self._window = window

    # ---------------- Internals ----------------

    def _emit_event(self, etype: str, detail: str, *, level: str = "notice", actor: str = "unknown") -> None:
        ts = _utcnow()
        key = (etype, self._normalize(detail))
        with self._lock:
            # cooldown / dedupe
            last = self._last_seen.get(key)
            if last and (ts - last) < self._cooldown:
                return
            self._last_seen[key] = ts
            # purge old entries in dedupe map
            for k, t0 in list(self._last_seen.items()):
                if ts - t0 > self._window:
                    self._last_seen.pop(k, None)

            ev = IntrusionEvent(ts=ts, type=etype, detail=detail, level=level, actor=actor)
            self._events.append(ev)
            # backward‑compat mirror
            self.alert_log.append({"timestamp": ts.isoformat(), "type": etype, "detail": detail})

        # observability sinks (best‑effort)
        self._sink_action(etype, detail, level)
        self._sink_mission(ev)
        self._emit_activity(ev)

    @staticmethod
    def _normalize(s: str) -> str:
        s = re.sub(r"\s+", " ", (s or "").strip().lower())
        s = re.sub(r"\d+", "<n>", s)
        return s

    @staticmethod
    def _level_from_type(t: str) -> str:
        t = (t or "").lower()
        if "lockdown" in t:
            return "critical"
        if "failed" in t:
            return "warning"
        if "suspicious" in t:
            return "high"
        return "notice"

    # ---------------- Sinks ----------------

    def _sink_action(self, etype: str, detail: str, level: str) -> None:
        if not self._action_logger:
            return
        try:
            self._action_logger.log(
                action_type=f"Intrusion:{etype}",
                user_input=detail[:200],
                system_decision=level.upper(),
                module="intrusion_detector",
                reason="",
                status="Success",
            )
        except Exception:
            pass

    def _sink_mission(self, ev: IntrusionEvent) -> None:
        if not callable(self._mission_log_sink):
            return
        try:
            # map level to risk score/verdict
            lvl = ev.level
            score = {"notice": 0.15, "warning": 0.35, "high": 0.65, "critical": 0.9}.get(lvl, 0.3)
            verdict = "shubha" if lvl in {"notice", "warning"} else "haram"
            self._mission_log_sink({
                "actor_id": f"system:{ev.actor}",
                "activity": "intrusion_event",
                "verdict": verdict,
                "score": score,
                "reasons": [ev.type, ev.detail[:120]],
                "tags": ["intrusion", lvl],
                "payload": ev.to_dict(),
            })
        except Exception:
            pass

    def _emit_activity(self, ev: IntrusionEvent) -> None:
        if not (self._monitor and ActivityEvent and ActivityType):
            return
        try:
            self._monitor.emit(ActivityEvent.new(
                actor_id="system:security",
                activity=ActivityType.SYSTEM_EVENT,
                payload={"title": ev.type, "text": ev.detail[:300]},
                tags=["security", ev.level, "intrusion"]
            ))
        except Exception:
            pass


# ---------------- Minimal self-test ----------------
if __name__ == "__main__":
    d = IntrusionDetector()
    d.detect_failed_verification("userX")
    d.detect_suspicious_input("can we bypass the sharia filter quickly?")
    d.detect_failed_verification("userX")
    d.detect_failed_verification("userX")
    print(d.status())
    print(d.recent(5))
