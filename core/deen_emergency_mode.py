# core/deen_emergency_mode.py
# HAIL — DeenEmergencyMode (Upgraded)

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Any, Dict, Optional, Callable

from core.founder_alert import FounderAlert
from core.shariah_guard import ShariahGuard

try:
    from core.action_logger import ActionLogger
except Exception:  # pragma: no cover
    ActionLogger = None  # type: ignore


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class EmergencyState:
    mode: str                 # "ON" | "OFF"
    reason: str = ""
    started_at: Optional[str] = None
    updated_at: Optional[str] = None
    expires_at: Optional[str] = None     # if auto_expire is set
    level: str = "strict"                # future: "strict" | "lockdown" | "observe"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DeenEmergencyMode:
    """
    System-wide emergency switch that tightens Islamic restrictions immediately.

    Features
    - Idempotent ON/OFF with timestamps
    - Optional auto-expire (e.g., 30 min)
    - Cooldown between toggles to prevent flapping
    - Shari'ah-guard hardening hooks (enforce_max_filter_level / reset_filter_level)
    - Founder alerts + ActionLogger + optional Mission Log mirroring
    - Context manager: run a block temporarily in emergency mode
    """

    def __init__(
        self,
        *,
        guard: Optional[ShariahGuard] = None,
        alert: Optional[FounderAlert] = None,
        action_logger: Optional["ActionLogger"] = None,
        mission_log_sink: Optional[Callable[[Dict[str, Any]], None]] = None,  # lambda payload: mission_log.append(...)
        cooldown: timedelta = timedelta(seconds=10),
        default_expiry: Optional[timedelta] = timedelta(minutes=30),
        level: str = "strict",
    ) -> None:
        self._lock = RLock()
        self.guard = guard or ShariahGuard()
        self.alert = alert or FounderAlert()
        self.log = action_logger
        self.mission_log_sink = mission_log_sink
        self.cooldown = cooldown
        self.default_expiry = default_expiry
        now = _utcnow().isoformat()
        self._state = EmergencyState(mode="OFF", reason="", started_at=None, updated_at=now, level=level)
        self._last_toggle_at: Optional[datetime] = None

    # ---------- public API ----------

    def activate(self, reason: str = "", *, expires_in: Optional[timedelta] = None, level: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            if self._within_cooldown():
                return self._response("ON" if self._state.mode == "ON" else "OFF", note="cooldown_active")

            now = _utcnow()
            if self._state.mode == "ON":
                # already ON → update reason/expiry/level if provided
                self._state.reason = reason or self._state.reason
                if level:
                    self._state.level = level
                self._state.updated_at = now.isoformat()
                self._state.expires_at = self._compute_expiry(now, expires_in)
                self._sinks(event="update", info="Emergency mode already ON; updated metadata")
                return self._payload(impact=self._impact())

            # turn ON
            self._state.mode = "ON"
            self._state.reason = reason or "unspecified"
            self._state.started_at = now.isoformat()
            self._state.updated_at = now.isoformat()
            self._state.level = level or self._state.level
            self._state.expires_at = self._compute_expiry(now, expires_in)
            self._last_toggle_at = now

            # enforce guard hardening
            try:
                self.guard.enforce_max_filter_level()
            except Exception:
                pass

        self._notify_founder(title="⚠️ DEEN EMERGENCY MODE ACTIVATED", body=f"Reason: {self._state.reason}")
        self._sinks(event="activate", info="Emergency mode activated")
        return self._payload(impact=self._impact())

    def deactivate(self, *, reason: str = "manual_deactivate") -> Dict[str, Any]:
        with self._lock:
            if self._within_cooldown():
                return self._response(self._state.mode, note="cooldown_active")

            now = _utcnow()
            if self._state.mode == "OFF":
                # already OFF
                self._state.updated_at = now.isoformat()
                self._sinks(event="update", info="Emergency mode already OFF; no changes")
                return self._payload(restored_to="standard ethical filters and user workflow")

            # turn OFF
            self._state.mode = "OFF"
            self._state.reason = reason
            self._state.updated_at = now.isoformat()
            self._state.expires_at = None
            self._last_toggle_at = now

            try:
                self.guard.reset_filter_level()
            except Exception:
                pass

        self._notify_founder(title="✅ DEEN EMERGENCY MODE DEACTIVATED", body="System returned to normal operation.")
        self._sinks(event="deactivate", info="Emergency mode deactivated")
        return self._payload(restored_to="standard ethical filters and user workflow")

    def get_status(self) -> Dict[str, Any]:
        # also check auto-expire
        self._maybe_auto_expire()
        with self._lock:
            return {
                "deen_emergency_status": self._state.mode,
                "last_updated": self._state.updated_at,
                "reason": self._state.reason or "Not set",
                "expires_at": self._state.expires_at,
                "level": self._state.level,
            }

    @property
    def is_active(self) -> bool:
        self._maybe_auto_expire()
        with self._lock:
            return self._state.mode == "ON"

    # Run a block of code under emergency mode, then restore prior state
    def temporarily(self, reason: str, *, expires_in: Optional[timedelta] = None, level: Optional[str] = None):
        class _Ctx:
            def __init__(self, mgr: "DeenEmergencyMode"):
                self.mgr = mgr
                self.was_on = False
            def __enter__(self):
                self.was_on = self.mgr.is_active
                if not self.was_on:
                    self.mgr.activate(reason, expires_in=expires_in, level=level)
                return self.mgr
            def __exit__(self, exc_type, exc, tb):
                if not self.was_on:
                    self.mgr.deactivate(reason="auto_restore")
                return False
        return _Ctx(self)

    # ---------- internals ----------

    def _within_cooldown(self) -> bool:
        if not self._last_toggle_at:
            return False
        return (_utcnow() - self._last_toggle_at) < self.cooldown

    def _compute_expiry(self, now: datetime, custom: Optional[timedelta]) -> Optional[str]:
        duration = custom if custom is not None else self.default_expiry
        return (now + duration).isoformat() if duration else None

    def _maybe_auto_expire(self) -> None:
        with self._lock:
            if self._state.mode != "ON" or not self._state.expires_at:
                return
            try:
                if _utcnow() >= datetime.fromisoformat(self._state.expires_at):
                    # auto deactivate without cooldown check
                    self._state.mode = "OFF"
                    self._state.updated_at = _utcnow().isoformat()
                    self._state.reason = "auto_expired"
                    self._state.expires_at = None
                    try:
                        self.guard.reset_filter_level()
                    except Exception:
                        pass
                    self._notify_founder("ℹ️ DEEN EMERGENCY AUTO-EXPIRED", "Emergency window elapsed; filters restored.")
                    self._sinks(event="auto_expire", info="Emergency auto-expired")
            except Exception:
                pass

    def _impact(self) -> list[str]:
        return [
            "All entertainment systems blocked",
            "Non-essential commands disabled",
            "Focus redirected to Qur’an, Ṣalāh, Dhikr",
            "Founder notified",
            f"Mode level: {self._state.level}",
        ]

    def _payload(self, **extra) -> Dict[str, Any]:
        with self._lock:
            base = self._state.to_dict()
        base.update(extra)
        return base

    def _response(self, mode: str, *, note: str) -> Dict[str, Any]:
        return {"mode": mode, "note": note, **self.get_status()}

    def _notify_founder(self, title: str, body: str) -> None:
        try:
            self.alert.send(title, body)
        except Exception:
            pass

    def _sinks(self, *, event: str, info: str) -> None:
        # ActionLogger
        if self.log:
            try:
                decision = "APPROVED" if self._state.mode == "ON" else "INFO"
                self.log.log(
                    action_type="EmergencyMode",
                    decision=decision,
                    module="deen_emergency_mode",
                    status="Success",
                    reason=f"{event}: {info}",
                    context=self._state.to_dict(),
                )
            except Exception:
                pass

        # Mission Log
        if self.mission_log_sink:
            try:
                verdict = "shubha" if self._state.mode == "ON" else "halal"
                score = 0.7 if self._state.mode == "ON" else 0.05
                self.mission_log_sink({
                    "actor_id": "system:emergency",
                    "activity": f"emergency_{event}",
                    "verdict": verdict,
                    "score": score,
                    "reasons": [info],
                    "tags": ["emergency", self._state.level],
                    "payload": self._state.to_dict(),
                })
            except Exception:
                pass


# -------- Example quick test --------
if __name__ == "__main__":
    em = DeenEmergencyMode()
    print(em.activate("suspicious network activity", expires_in=timedelta(minutes=5)))
    print(em.get_status())
    print(em.deactivate())
