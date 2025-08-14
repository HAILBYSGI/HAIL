# core/taqwa_sensitivity_controller.py
# Phase 3 — Taqwa Sensitivity
# Tracks & adjusts a 0–100 taqwa level with smoothing, history, and observers.
# Backwards compatible with: adjust_taqwa(), get_current_level(), is_alert(), get_history(), reset_taqwa()

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from threading import RLock
from typing import Callable, Dict, List, Optional
import json


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class TaqwaEvent:
    ts: datetime
    context: str
    change: int                # +/− integer applied
    new_level: int             # clamped 0..100
    source: str = "system"
    actor_id: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ts"] = self.ts.isoformat()
        return d


class TaqwaSensitivityController:
    """
    - Level 0..100 (0 = dull, 100 = hyper-aware)
    - EWMA smoothing for stability
    - Thread-safe, with simple pub/sub for downstream modules (monitor/guardian)
    """

    def __init__(self, base_level: int = 50, ewma_alpha: float = 0.25, history_limit: int = 500):
        self._lock = RLock()
        self._level = int(max(0, min(100, base_level)))
        self._ewma = float(self._level)               # smoothed view (0..100)
        self._alpha = max(0.01, min(1.0, ewma_alpha)) # smoothing factor
        self._history: List[TaqwaEvent] = []
        self._history_limit = max(50, history_limit)
        self._subs: List[Callable[[int, float, TaqwaEvent], None]] = []

    # ------------- Compatibility API -------------

    def adjust_taqwa(self, context: str, increase: bool = True, value: int = 5,
                     *, actor_id: Optional[str] = None, source: str = "system") -> Dict[str, object]:
        """
        Adjust level by ±value (int). Keeps history and updates EWMA.
        Returns a dict (compatible with your original).
        """
        delta = int(value if increase else -value)
        with self._lock:
            self._level = int(max(0, min(100, self._level + delta)))
            self._ewma = (1 - self._alpha) * self._ewma + self._alpha * float(self._level)

            ev = TaqwaEvent(ts=_now(), context=context, change=delta, new_level=self._level,
                            source=source, actor_id=actor_id)
            self._history.append(ev)
            if len(self._history) > self._history_limit:
                self._history = self._history[-self._history_limit:]

            # notify subscribers (best-effort)
            for fn in list(self._subs):
                try:
                    fn(self._level, self._ewma, ev)
                except Exception:
                    pass

            return {
                "status": "updated",
                "taqwa_level": self._level,
                "context": context
            }

    def get_current_level(self) -> int:
        with self._lock:
            return self._level

    def is_alert(self):
        """
        Backwards behavior:
          True  -> high sensitivity (>=80)
          False -> dangerously low (<=20)
          None  -> normal
        """
        with self._lock:
            if self._level >= 80:
                return True
            if self._level <= 20:
                return False
            return None

    def get_history(self) -> List[Dict[str, object]]:
        with self._lock:
            return [e.to_dict() for e in self._history]

    def reset_taqwa(self) -> str:
        with self._lock:
            self._level = 50
            self._ewma = 50.0
            self._history.clear()
            return "🔄 Taqwa sensitivity reset to neutral level (50)."

    # ------------- Extended API -------------

    def set_level(self, level: int, *, context: str = "set_level", actor_id: Optional[str] = None, source: str = "system"):
        level = int(max(0, min(100, level)))
        with self._lock:
            delta = level - self._level
            self._level = level
            self._ewma = (1 - self._alpha) * self._ewma + self._alpha * float(self._level)
            ev = TaqwaEvent(ts=_now(), context=context, change=delta, new_level=self._level, source=source, actor_id=actor_id)
            self._history.append(ev)
            if len(self._history) > self._history_limit:
                self._history = self._history[-self._history_limit:]
            for fn in list(self._subs):
                try: fn(self._level, self._ewma, ev)
                except Exception: pass

    def get_level_normalized(self) -> float:
        with self._lock:
            return round(self._level / 100.0, 4)

    def get_ewma(self) -> float:
        with self._lock:
            return round(self._ewma, 3)

    def subscribe(self, cb: Callable[[int, float, TaqwaEvent], None]) -> None:
        with self._lock:
            self._subs.append(cb)

    def export_json(self) -> str:
        with self._lock:
            return json.dumps({
                "level": self._level,
                "ewma": round(self._ewma, 3),
                "history": [e.to_dict() for e in self._history]
            }, ensure_ascii=False, indent=2)


# ------- Optional: helpers to plug into DeenSystemRefresher hooks -------

def make_read_taqwa_hook(controller: TaqwaSensitivityController):
    """
    Returns a hook: () -> (ok: bool, details: dict)
    Shape matches DeenSystemRefresher.read_taqwa_level
    """
    def _hook():
        return True, {"taqwa": f"{controller.get_level_normalized():.2f}", "ewma": f"{controller.get_ewma():.2f}"}
    return _hook

def make_broadcast_taqwa_hook(controller: TaqwaSensitivityController, monitor: Optional[object] = None):
    """
    Returns a hook: (level_float) -> (ok: bool, details: dict)
    You can pass your DeenActivityMonitor instance to gently apply sensitivity.
    """
    def _hook(level: float):
        # Optionally nudge internal level to what refresher read (idempotent)
        controller.set_level(int(round(level * 100)), context="refresher_broadcast", source="refresher")
        # If a monitor is provided and supports setting taqwa_sensitivity, apply it
        applied = False
        try:
            if monitor and hasattr(monitor, "cfg"):
                monitor.cfg.taqwa_sensitivity = float(level)
                applied = True
        except Exception:
            applied = False
        return True, {"broadcast_to": "controller" + (", monitor" if applied else ""), "level": f"{level:.2f}"}
    return _hook
