# core/system_trust_score.py
# Phase 3 — Integrity & Observability
# Purpose: Track per-module trust (0..100), decay over time, and provide
#          structured adjustments with reasons. Safe for concurrent use.

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Dict, List, Optional, Callable


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class TrustEvent:
    ts: datetime
    module: str
    before: int
    after: int
    delta: int
    reason: str
    actor: str = "system"  # who triggered the change (module, admin, founder, etc.)


class SystemTrustScore:
    """
    - Module scores clamped to [0, 100] (default 100).
    - Time decay (e.g., -d points per day without positive events).
    - Thread-safe operations.
    - Optional logger hook: on_log(module, action, status, metadata)
    """

    def __init__(
        self,
        base: int = 100,
        decay_per_day: int = 0,            # set >0 to enable passive decay
        min_score: int = 0,
        max_score: int = 100,
        on_log: Optional[Callable[[str, str, str, dict], None]] = None,
    ):
        self._base = int(base)
        self._min = int(min_score)
        self._max = int(max_score)
        self._decay_per_day = max(0, int(decay_per_day))
        self._scores: Dict[str, int] = {}
        self._last_touch: Dict[str, datetime] = {}
        self._history: List[TrustEvent] = []
        self._lock = RLock()
        self._log = on_log

    # ---------- public API ----------

    def initialize_module(self, module: str, base_score: Optional[int] = None) -> None:
        with self._lock:
            if module not in self._scores:
                score = self._clamp(base_score if base_score is not None else self._base)
                self._scores[module] = score
                self._last_touch[module] = _now()
                self._emit_log(module, "trust_init", "OK", {"score": score})

    def adjust_score(self, module: str, change: int, reason: str = "", actor: str = "system") -> TrustEvent:
        with self._lock:
            self._ensure(module)
            self._apply_decay(module)

            before = self._scores[module]
            after = self._clamp(before + int(change))
            self._scores[module] = after
            self._last_touch[module] = _now()

            evt = TrustEvent(ts=_now(), module=module, before=before, after=after, delta=int(change), reason=reason, actor=actor)
            self._history.append(evt)
            self._emit_log(module, "trust_adjust", "OK", {"before": before, "after": after, "delta": change, "reason": reason, "actor": actor})
            return evt

    def penalize(self, module: str, points: int, reason: str, actor: str = "system") -> TrustEvent:
        return self.adjust_score(module, -abs(points), reason, actor)

    def reward(self, module: str, points: int, reason: str, actor: str = "system") -> TrustEvent:
        return self.adjust_score(module, abs(points), reason, actor)

    def get_score(self, module: str) -> int:
        with self._lock:
            self._ensure(module)
            self._apply_decay(module)
            return self._scores[module]

    def get_all_scores(self) -> Dict[str, int]:
        with self._lock:
            # apply decay lazily for all before returning snapshot
            for m in list(self._scores.keys()):
                self._apply_decay(m)
            return dict(self._scores)

    def flag_low_trust_modules(self, threshold: int = 50) -> List[str]:
        with self._lock:
            flagged = []
            for m in list(self._scores.keys()):
                self._apply_decay(m)
                if self._scores[m] < threshold:
                    flagged.append(m)
            return flagged

    def reset_score(self, module: str, score: Optional[int] = None, reason: str = "reset", actor: str = "system") -> TrustEvent:
        with self._lock:
            self._ensure(module)
            before = self._scores[module]
            after = self._clamp(self._base if score is None else int(score))
            self._scores[module] = after
            self._last_touch[module] = _now()
            evt = TrustEvent(ts=_now(), module=module, before=before, after=after, delta=after - before, reason=reason, actor=actor)
            self._history.append(evt)
            self._emit_log(module, "trust_reset", "OK", {"before": before, "after": after, "reason": reason, "actor": actor})
            return evt

    def history(self, limit: Optional[int] = None) -> List[dict]:
        with self._lock:
            items = self._history[-limit:] if (limit and limit > 0) else self._history
            return [self._event_to_dict(e) for e in items]

    # ---------- internals ----------

    def _ensure(self, module: str) -> None:
        if module not in self._scores:
            self._scores[module] = self._clamp(self._base)
            self._last_touch[module] = _now()
            self._emit_log(module, "trust_autoinit", "OK", {"score": self._scores[module]})

    def _apply_decay(self, module: str) -> None:
        if self._decay_per_day <= 0:
            return
        last = self._last_touch.get(module)
        if not last:
            self._last_touch[module] = _now()
            return
        now = _now()
        # whole-day granularity to avoid micro adjustments every call
        days = int((now - last).total_seconds() // 86_400)
        if days > 0:
            dec = self._decay_per_day * days
            before = self._scores[module]
            after = self._clamp(before - dec)
            if after != before:
                self._scores[module] = after
                evt = TrustEvent(ts=now, module=module, before=before, after=after, delta=-(dec), reason=f"decay:{days}d", actor="system")
                self._history.append(evt)
                self._emit_log(module, "trust_decay", "OK", {"days": days, "before": before, "after": after})
            self._last_touch[module] = now

    def _clamp(self, val: int) -> int:
        return max(self._min, min(self._max, int(val)))

    def _event_to_dict(self, e: TrustEvent) -> dict:
        d = asdict(e)
        d["ts"] = e.ts.isoformat()
        return d

    def _emit_log(self, module: str, action: str, status: str, meta: dict) -> None:
        if self._log:
            try:
                self._log(module, action, status, meta)
            except Exception:
                pass


# ---------- quick self-check ----------
if __name__ == "__main__":
    def demo_log(mod, act, st, meta):  # optional logger hook
        print(f"[LOG] {mod}::{act} -> {st} | {meta}")

    sts = SystemTrustScore(decay_per_day=3, on_log=demo_log)
    sts.initialize_module("ActionBlocker")
    print("score:", sts.get_score("ActionBlocker"))
    sts.penalize("ActionBlocker", 12, "blocked false positive", actor="qa")
    sts.reward("ActionBlocker", 5, "corrected rule", actor="maint")
    print("all:", sts.get_all_scores())
    print("history:", sts.history())
