# core/fallback_shield.py
# HAIL — FallbackShield (Upgraded)
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Optional

# Optional sinks (best-effort; no hard dependency)
try:
    from core.action_logger import ActionLogger  # type: ignore
except Exception:  # pragma: no cover
    ActionLogger = None  # type: ignore


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ShieldEvent:
    status: str                 # "ACTIVATED" | "DEACTIVATED"
    timestamp: str              # ISO8601 UTC
    reason: str
    level: str = "high"         # "low" | "medium" | "high" | "critical"
    actor: str = "system"       # "system" | "founder" | "guardian"
    meta: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if d["meta"] is None:
            d.pop("meta")
        return d


class FallbackShield:
    """
    Emergency safety layer that can be activated on critical conditions
    (tamper, override attempts, ethics violations) and only deactivated by
    verified Founder confirmation.
    - Thread‑safe
    - Text + JSONL logs with rotation
    - Optional sinks: ActionLogger + Mission Log
    - Cooldown guard to avoid log spam on repeated triggers
    """

    VALID_LEVELS = {"low", "medium", "high", "critical"}

    def __init__(
        self,
        shield_log_path: str = "hail_logs/fallback_log.txt",       # kept for backward compatibility (text log)
        *,
        json_log_path: str = "hail/logs/fallback_log.jsonl",       # structured log
        max_bytes: int = 2_000_000,
        keep_backups: int = 5,
        cooldown: timedelta = timedelta(seconds=10),
        founder_verifier: Optional[callable] = None,               # optional callable() -> bool
        mission_log_sink: Optional[callable] = None,               # lambda payload: mission_log.append(...)
    ) -> None:
        # legacy text log (your original path)
        self._text_path = Path(shield_log_path)
        self._text_path.parent.mkdir(parents=True, exist_ok=True)

        # structured JSONL log
        self._jsonl_path = Path(json_log_path)
        self._jsonl_path.parent.mkdir(parents=True, exist_ok=True)

        self._max_bytes = int(max_bytes)
        self._keep_backups = int(keep_backups)
        self._cooldown = cooldown
        self._founder_verifier = founder_verifier
        self._mission_log_sink = mission_log_sink

        self._lock = RLock()
        self.active: bool = False
        self.trigger_reason: Optional[str] = None
        self.trigger_time: Optional[datetime] = None
        self._last_activation_at: Optional[datetime] = None

        # Optional ActionLogger
        self._action_logger = ActionLogger() if ActionLogger else None

    # ---------------- Public API (backward compatible) ----------------

    def activate(self, reason: str, *, level: str = "high", meta: Optional[Dict[str, Any]] = None) -> None:
        """
        Triggers the fallback system and logs the event.
        Backward compatible signature: activate(reason)
        """
        lvl = (level or "high").lower().strip()
        if lvl not in self.VALID_LEVELS:
            lvl = "high"

        now = datetime.now(timezone.utc)
        with self._lock:
            # cooldown to prevent spam activation storm
            if self._last_activation_at and (now - self._last_activation_at) < self._cooldown and self.active:
                # still refresh reason/time for visibility but skip duplicate heavy logs
                self.trigger_reason = reason
                self.trigger_time = now
                return

            self.active = True
            self.trigger_reason = reason
            self.trigger_time = now
            self._last_activation_at = now

            ev = ShieldEvent(status="ACTIVATED", timestamp=_utc_iso(), reason=reason, level=lvl, actor="system", meta=meta)
            self._write_logs(ev)

        # sinks
        self._sink_action(ev)
        self._sink_mission(ev, verdict="shubha" if lvl in {"low", "medium"} else "haram", score=0.6 if lvl in {"low", "medium"} else 0.9)

    def deactivate(self, founder_confirmed: bool = False, *, meta: Optional[Dict[str, Any]] = None) -> bool:
        """
        Deactivates shield only if founder confirms.
        Backward compatible signature: deactivate(founder_confirmed=False)
        """
        with self._lock:
            verified = bool(founder_confirmed)
            if not verified and self._founder_verifier:
                try:
                    verified = bool(self._founder_verifier())
                except Exception:
                    verified = False

            if not verified:
                return False

            self.active = False
            self.trigger_reason = None
            self.trigger_time = None

            ev = ShieldEvent(status="DEACTIVATED", timestamp=_utc_iso(), reason="Founder override verified.", level="low", actor="founder", meta=meta)
            self._write_logs(ev)

        # sinks
        self._sink_action(ev)
        self._sink_mission(ev, verdict="halal", score=0.05)
        return True

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "active": self.active,
                "trigger_reason": self.trigger_reason,
                "trigger_time": self.trigger_time.strftime("%Y-%m-%d %H:%M:%S") if self.trigger_time else "None",
            }

    # ---------------- Convenience (new) ----------------

    def history(self, n: int = 100) -> Any:
        """Return the last n structured events from JSONL."""
        if not self._jsonl_path.exists():
            return []
        with self._jsonl_path.open("r", encoding="utf-8") as f:
            rows = f.readlines()[-int(n):]
        out = []
        for r in rows:
            try:
                out.append(json.loads(r))
            except Exception:
                continue
        return out

    # ---------------- Internals ----------------

    def _write_logs(self, ev: ShieldEvent) -> None:
        # rotate if needed
        self._rotate_if_needed_unlocked(self._text_path)
        self._rotate_if_needed_unlocked(self._jsonl_path)
        # text (legacy compatible)
        with self._text_path.open("a", encoding="utf-8") as f:
            f.write(self._format_text(ev) + "\n")
        # jsonl
        with self._jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(ev.to_dict(), ensure_ascii=False) + "\n")

    @staticmethod
    def _format_text(ev: ShieldEvent) -> str:
        lvl = ev.level.upper()
        return f"---\nStatus     : {ev.status}\nTimestamp  : {ev.timestamp}\nLevel      : {lvl}\nReason     : {ev.reason}\n"

    def _rotate_if_needed_unlocked(self, path: Path) -> None:
        try:
            if path.exists() and path.stat().st_size > self._max_bytes:
                ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
                rotated = path.with_name(f"{path.stem}.{ts}{path.suffix}")
                shutil.copy2(path, rotated)
                path.unlink(missing_ok=True)
                # keep last N backups
                family = sorted(path.parent.glob(f"{path.stem}.*{path.suffix}"), reverse=True)
                for old in family[self._keep_backups:]:
                    try:
                        old.unlink()
                    except OSError:
                        pass
        except Exception:
            # never crash shield on rotation issues
            pass

    # ---------------- Sinks ----------------

    def _sink_action(self, ev: ShieldEvent) -> None:
        if not self._action_logger:
            return
        try:
            self._action_logger.log(
                action_type="FallbackShield",
                user_input=ev.reason[:160],
                system_decision=ev.status,
                module="fallback_shield",
                reason=f"level={ev.level}",
                status="Success",
            )
        except Exception:
            pass

    def _sink_mission(self, ev: ShieldEvent, *, verdict: str, score: float) -> None:
        if not self._mission_log_sink:
            return
        try:
            self._mission_log_sink({
                "actor_id": f"{ev.actor}",
                "activity": "fallback_shield",
                "verdict": verdict,
                "score": float(score),
                "reasons": [f"{ev.status.lower()} ({ev.level})", ev.reason[:120]],
                "tags": ["shield", ev.level, ev.status.lower()],
                "payload": ev.to_dict(),
            })
        except Exception:
            pass


# ---------------- Example usage ----------------
if __name__ == "__main__":
    shield = FallbackShield()
    shield.activate("Unauthorized system modification attempt", level="critical")
    print(shield.status())
    ok = shield.deactivate(founder_confirmed=False)
    print("Founder denied deactivation:", not ok)
