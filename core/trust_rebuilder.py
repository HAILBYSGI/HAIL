# core/trust_rebuilder.py
# Phase 3 — Trust & Reputation
# Backward compatible with your original "TrustRebuilderd" API, but sturdier:
# - Clamp 0..100, structured reasons, optional weights
# - Thresholds (warn/danger) + simple subscribers for downstream actions
# - JSON persistence (so trust survives restarts)
# - Export/import + compact snapshot

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from threading import RLock
from typing import Callable, Dict, List, Optional
import json
import os


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class TrustEvent:
    ts: datetime
    action: str            # 'degrade' | 'rebuild' | 'reset' | 'set'
    reason: str
    change: int
    new_score: int

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ts"] = self.ts.isoformat()
        return d


class TrustRebuilder:
    """
    Trust score manager (0..100) with logs, persistence, and alerts.
    Backward-compatible methods maintained:
      - degrade_trust(reason, points=10)
      - rebuild_trust(action, points=5)
      - get_trust_score()
      - get_repair_logs()
      - reset_trust()
    """

    def __init__(
        self,
        *,
        base: int = 100,
        state_file: str = "logs/trust_state.json",
        warn_threshold: int = 60,
        danger_threshold: int = 30,
        history_limit: int = 1000,
    ):
        self._lock = RLock()
        self._score = int(max(0, min(100, base)))
        self._events: List[TrustEvent] = []
        self._subs: List[Callable[[int, TrustEvent], None]] = []
        self._state_file = state_file
        self._warn_th = int(max(0, min(100, warn_threshold)))
        self._danger_th = int(max(0, min(100, danger_threshold)))
        self._history_limit = max(100, history_limit)

        # Prepare directory
        os.makedirs(os.path.dirname(self._state_file) or ".", exist_ok=True)
        # Load last state if present
        self._load_state()

    # ---------- Backward-compatible API ----------

    def degrade_trust(self, reason: str, points: int = 10) -> str:
        return self._apply(delta=-abs(int(points)), reason=reason, action="degrade")

    def rebuild_trust(self, action: str, points: int = 5) -> str:
        return self._apply(delta=abs(int(points)), reason=action, action="rebuild")

    def get_trust_score(self) -> int:
        with self._lock:
            return self._score

    def get_repair_logs(self) -> List[dict]:
        with self._lock:
            return [e.to_dict() for e in self._events]

    def reset_trust(self) -> str:
        with self._lock:
            self._score = 100
            ev = TrustEvent(ts=_now(), action="reset", reason="manual_reset", change=0, new_score=self._score)
            self._append_event(ev)
            self._save_state()
            self._notify(ev)
            return "🔄 Trust score reset to 100 and logs cleared."

    # ---------- Extended API ----------

    def set_score(self, value: int, reason: str = "set"):
        value = int(max(0, min(100, value)))
        with self._lock:
            delta = value - self._score
            self._score = value
            ev = TrustEvent(ts=_now(), action="set", reason=reason, change=delta, new_score=self._score)
            self._append_event(ev)
            self._save_state()
            self._notify(ev)

    def auto_decay(self, per_day: int = 2, reason: str = "auto_decay", now: Optional[datetime] = None):
        """
        Optional scheduled decay to gradually recover (positive per_day) or erode (negative).
        """
        if per_day == 0:
            return
        dt = now or _now()
        delta = int(per_day)  # positive = rebuild, negative = degrade
        self._apply(delta=delta, reason=reason, action="rebuild" if delta > 0 else "degrade")

    def status(self) -> Dict[str, object]:
        with self._lock:
            level = "ok"
            if self._score <= self._danger_th:
                level = "danger"
            elif self._score <= self._warn_th:
                level = "warn"
            return {
                "score": self._score,
                "level": level,
                "warn_threshold": self._warn_th,
                "danger_threshold": self._danger_th,
                "events": len(self._events),
            }

    def set_thresholds(self, *, warn: Optional[int] = None, danger: Optional[int] = None):
        with self._lock:
            if warn is not None:
                self._warn_th = int(max(0, min(100, warn)))
            if danger is not None:
                self._danger_th = int(max(0, min(100, danger)))
            self._save_state()

    def subscribe(self, fn: Callable[[int, TrustEvent], None]):
        """Register a callback(level:int, last_event:TrustEvent) -> None"""
        with self._lock:
            self._subs.append(fn)

    def export_json(self) -> str:
        with self._lock:
            return json.dumps(
                {
                    "score": self._score,
                    "warn_threshold": self._warn_th,
                    "danger_threshold": self._danger_th,
                    "events": [e.to_dict() for e in self._events],
                },
                ensure_ascii=False,
                indent=2,
            )

    # ---------- Internals ----------

    def _apply(self, *, delta: int, reason: str, action: str) -> str:
        with self._lock:
            old = self._score
            self._score = int(max(0, min(100, self._score + delta)))
            ev = TrustEvent(ts=_now(), action=action, reason=reason, change=delta, new_score=self._score)
            self._append_event(ev)
            self._save_state()
            self._notify(ev)
            if delta < 0:
                return f"⚠️ Trust score decreased to {self._score} due to: {reason}"
            else:
                return f"✅ Trust score increased to {self._score} after: {reason}"

    def _append_event(self, ev: TrustEvent):
        self._events.append(ev)
        if len(self._events) > self._history_limit:
            self._events = self._events[-self._history_limit:]

    def _notify(self, ev: TrustEvent):
        for fn in list(self._subs):
            try:
                fn(self._score, ev)
            except Exception:
                pass

    def _save_state(self):
        try:
            with open(self._state_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "score": self._score,
                        "warn_threshold": self._warn_th,
                        "danger_threshold": self._danger_th,
                        "events": [e.to_dict() for e in self._events],
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception:
            pass

    def _load_state(self):
        if not os.path.exists(self._state_file):
            return
        try:
            with open(self._state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._score = int(max(0, min(100, data.get("score", self._score))))
            self._warn_th = int(max(0, min(100, data.get("warn_threshold", self._warn_th))))
            self._danger_th = int(max(0, min(100, data.get("danger_threshold", self._danger_th))))
            evs = data.get("events", [])
            self._events = []
            for d in evs:
                self._events.append(
                    TrustEvent(
                        ts=datetime.fromisoformat(d["ts"]),
                        action=d["action"],
                        reason=d["reason"],
                        change=int(d["change"]),
                        new_score=int(d["new_score"]),
                    )
                )
        except Exception:
            # If corrupted, keep runtime defaults and continue
            pass


# Backward name alias if you already imported TrustRebuilderd elsewhere
TrustRebuilderd = TrustRebuilder

if __name__ == "__main__":
    tr = TrustRebuilder()
    print(tr.degrade_trust("unverified_action", 12))
    print(tr.rebuild_trust("founder_review_ok", 8))
    print(tr.status())
    print(tr.export_json())
