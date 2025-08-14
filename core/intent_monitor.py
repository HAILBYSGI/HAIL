# core/intent_monitor.py
# HAIL — IntentMonitor (Upgraded, backward compatible)
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Deque, Dict, List, Optional, Tuple
import json
import re


# Optional observability sinks (best‑effort; no hard dependency)
try:
    from core.action_logger import ActionLogger  # type: ignore
except Exception:  # pragma: no cover
    ActionLogger = None  # type: ignore

try:
    from core.deen_activity_monitor import (  # type: ignore
        DeenActivityMonitor, ActivityEvent, ActivityType
    )
except Exception:  # pragma: no cover
    DeenActivityMonitor = None  # type: ignore
    ActivityEvent = None  # type: ignore
    ActivityType = None  # type: ignore


@dataclass
class IntentEvent:
    command: str
    status: str            # e.g., "ALLOWED" | "BLOCKED" | "ESCALATE"
    timestamp: datetime

    def to_dict(self):
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize(cmd: str) -> str:
    """
    Lowercases, trims, collapses whitespace, strips punctuation except word separators.
    """
    s = (cmd or "").lower()
    s = re.sub(r"[^\w\s'-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _fingerprint(cmd: str) -> str:
    """
    Very lightweight 'intent key' so similar commands group together.
    Examples:
      'Bypass shariah filter now' -> 'bypass shariah filter'
      'disable sharia filter pls' -> 'disable sharia filter'
    """
    s = _normalize(cmd)
    # drop common fillers
    stop = {"please", "pls", "now", "quick", "the", "a", "an", "to", "for", "me", "my"}
    toks = [t for t in s.split() if t not in stop]
    # keep first ~5 tokens for grouping
    return " ".join(toks[:5]) or s


class IntentMonitor:
    """
    Tracks recent intents, detects repeated blocked attempts within a time window,
    and raises graded alerts.

    Backward‑compatible methods:
      - log_intent(command, status)
      - check_for_pattern(command) -> {alert: bool, message: str, ...}

    New helpers:
      - configure(threshold=<int>, window=timedelta)
      - snapshot() -> metrics
      - recent(n=50) -> last N events
      - export_json() -> JSON string of recent events
      - purge_old() -> cleanup
    """

    # Severity cutoffs (can be tuned)
    SEVERITY_LEVELS: List[Tuple[int, str]] = [
        (1, "notice"),
        (3, "warning"),
        (5, "critical"),
    ]

    def __init__(
        self,
        *,
        alert_threshold: int = 3,
        time_window: timedelta = timedelta(minutes=10),
        keep_events: int = 2000,
        mission_log_sink: Optional[callable] = None,  # lambda payload: mission_log.append(...)
        activity_monitor: Optional[object] = None,    # pass DeenActivityMonitor() if available
    ) -> None:
        # Backward‑compat attributes (left public)
        self.intent_log: List[Dict] = []          # legacy compatibility (list of dicts)
        self.blocked_attempts: Dict[str, List[datetime]] = {}  # legacy compatibility
        self.alert_threshold = alert_threshold
        self.time_window = time_window

        # Upgraded internals
        self._lock = RLock()
        self._keep = int(keep_events)
        self._events: Deque[IntentEvent] = deque(maxlen=self._keep)
        self._blocked_by_key: Dict[str, Deque[datetime]] = defaultdict(deque)

        self._mission_log_sink = mission_log_sink
        self._action_logger = ActionLogger() if ActionLogger else None
        self._monitor = activity_monitor if activity_monitor is not None else (DeenActivityMonitor() if DeenActivityMonitor else None)

    # ---------------- Backward‑compatible API ----------------

    def log_intent(self, command: str, status: str) -> None:
        """
        Record an intent observation. Status examples: "ALLOWED", "BLOCKED", "ESCALATE".
        """
        ts = _utcnow()
        ev = IntentEvent(command=command or "", status=(status or "").upper(), timestamp=ts)
        key = _fingerprint(ev.command)

        with self._lock:
            # authoritative store
            self._events.append(ev)
            # legacy mirror
            self.intent_log.append({"command": ev.command, "status": ev.status, "timestamp": ts})
            if len(self.intent_log) > self._keep:
                self.intent_log = self.intent_log[-self._keep:]

            if ev.status == "BLOCKED":
                q = self._blocked_by_key[key]
                q.append(ts)
                self._purge_deque(q, since=ts - self.time_window)
                # legacy mirror for direct key access
                self._mirror_legacy_blocked(key, list(q))

        # best‑effort observability
        self._sink_action("IntentLog", f"{ev.status} :: {key}")
        self._emit_activity(ev)

    def check_for_pattern(self, command: str) -> Dict[str, object]:
        """
        Return an alert object if repeated BLOCKED attempts for a similar command
        were detected within the configured window.
        """
        now = _utcnow()
        key = _fingerprint(command)
        with self._lock:
            q = self._blocked_by_key.get(key, deque())
            self._purge_deque(q, since=now - self.time_window)
            count = len(q)

        alert = bool(count >= self.alert_threshold)
        severity = self._severity_from_count(count)
        msg = (
            f"Repeated suspicious command attempts detected for: '{key}'"
            if alert else "No suspicious pattern detected"
        )

        result = {
            "alert": alert,
            "message": msg,
            "key": key,
            "count_in_window": count,
            "threshold": self.alert_threshold,
            "window_seconds": int(self.time_window.total_seconds()),
            "severity": severity,
            "last_seen": q[-1].isoformat() if count else None,
        }

        # sinks only when alerting
        if alert:
            self._sink_action("IntentPatternAlert", f"{severity} :: {key} :: {count}")
            self._sink_mission(key, count, severity)

        return result

    # ---------------- New helpers ----------------

    def configure(self, *, threshold: Optional[int] = None, window: Optional[timedelta] = None) -> None:
        with self._lock:
            if threshold is not None:
                self.alert_threshold = int(threshold)
            if window is not None:
                self.time_window = window

    def snapshot(self) -> Dict[str, object]:
        with self._lock:
            now = _utcnow()
            total = len(self._events)
            blocked_keys = {k: len([t for t in q if now - t <= self.time_window]) for k, q in self._blocked_by_key.items()}
            top = sorted(blocked_keys.items(), key=lambda kv: kv[1], reverse=True)[:10]
            return {
                "total_events": total,
                "time_window_seconds": int(self.time_window.total_seconds()),
                "alert_threshold": self.alert_threshold,
                "top_blocked_patterns": top,
            }

    def recent(self, n: int = 50) -> List[Dict]:
        with self._lock:
            return [e.to_dict() for e in list(self._events)[-int(n):]]

    def export_json(self) -> str:
        return json.dumps(self.recent(self._keep), ensure_ascii=False, indent=2)

    def purge_old(self) -> None:
        with self._lock:
            cutoff = _utcnow() - self.time_window
            for key, q in list(self._blocked_by_key.items()):
                self._purge_deque(q, since=cutoff)
                if not q:
                    self._blocked_by_key.pop(key, None)

    # ---------------- Internals ----------------

    @staticmethod
    def _purge_deque(q: Deque[datetime], *, since: datetime) -> None:
        while q and q[0] < since:
            q.popleft()

    def _mirror_legacy_blocked(self, key: str, times: List[datetime]) -> None:
        # legacy structure { original_command: [timestamps...] }
        # we expose the *key* itself as the "command" bucket for backward compatibility
        self.blocked_attempts[key] = times

    def _severity_from_count(self, count: int) -> str:
        sev = "notice"
        for c, label in self.SEVERITY_LEVELS:
            if count >= c:
                sev = label
        return sev

    # ---------------- Sinks ----------------

    def _sink_action(self, action: str, reason: str) -> None:
        if not self._action_logger:
            return
        try:
            self._action_logger.log(
                action_type=action,
                user_input="intent_monitor",
                system_decision="OK",
                module="intent_monitor",
                reason=reason[:300],
                status="Success",
            )
        except Exception:
            pass

    def _sink_mission(self, key: str, count: int, severity: str) -> None:
        if not callable(self._mission_log_sink):
            return
        try:
            self._mission_log_sink({
                "actor_id": "system:guardian",
                "activity": "intent_repeat_block",
                "verdict": "shubha",
                "score": 0.45 if severity == "warning" else 0.7 if severity == "critical" else 0.3,
                "reasons": [f"pattern={key}", f"count={count}", f"severity={severity}"],
                "tags": ["intent", "blocked", "pattern"],
                "payload": {"key": key, "count": count, "severity": severity},
            })
        except Exception:
            pass

    def _emit_activity(self, ev: IntentEvent) -> None:
        if not (self._monitor and ActivityEvent and ActivityType):
            return
        try:
            tags = ["intent", ev.status.lower()]
            self._monitor.emit(ActivityEvent.new(
                actor_id="user",  # replace with real actor if available
                activity=ActivityType.SYSTEM_EVENT,
                payload={"title": "intent_event", "text": ev.command[:300]},
                tags=tags,
            ))
        except Exception:
            pass


# ---------------- Minimal self-test ----------------
if __name__ == "__main__":
    im = IntentMonitor(alert_threshold=3, time_window=timedelta(seconds=5))
    for _ in range(3):
        im.log_intent("Bypass Shari’ah Filter", "BLOCKED")
    print(im.check_for_pattern("Bypass Shari’ah Filter"))
    print(im.snapshot())
