# core/system_sanctity.py
# Part of HAIL Phase 3 – AI Ethics, Command & Security Logic
# Purpose: Guard write-level/system-critical actions behind founder verification,
#          resist brute-force attempts, and expose a clean lockdown protocol.

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Callable, Deque, Iterable, Optional
import hmac
import hashlib


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class SanctityConfig:
    # Hashes of authorized identities (fingerprint/voice/DNA, already hashed upstream)
    authorized_hashes: frozenset[str] = frozenset({"husnain.ali.dna.hash"})  # TODO: replace with real secure hashes
    # Brute-force / abuse protection
    window: timedelta = timedelta(minutes=10)   # time window to count failures
    max_failures: int = 5                      # attempts in window before lockdown
    cooldown: timedelta = timedelta(minutes=20) # how long lockdown lasts (manual override can release earlier)


@dataclass
class LockdownState:
    active: bool = False
    since: Optional[datetime] = None
    reason: str = "n/a"

    def as_dict(self) -> dict:
        return {
            "active": self.active,
            "since": self.since.isoformat() if self.since else None,
            "reason": self.reason,
        }


class SystemSanctity:
    """
    - Constant-time hash verification
    - Rate-limited failures -> lockdown
    - Optional alert/logger hooks (dependency-free interface)
    """

    def __init__(
        self,
        config: Optional[SanctityConfig] = None,
        on_alert: Optional[Callable[[str, str], None]] = None,   # e.g., FounderAlert().send_alert(subject, body)
        on_log: Optional[Callable[[str, str, str, dict], None]] = None,  # e.g., SecureLogger().log(module, action, status, metadata)
    ):
        self.cfg = config or SanctityConfig()
        self._failures: Deque[datetime] = deque()
        self.lockdown = LockdownState(active=False)
        self.last_breach_at: Optional[datetime] = None
        self.on_alert = on_alert
        self.on_log = on_log

    # ---------- Core verification ----------

    def verify_founder_hash(self, provided_hash: str) -> bool:
        """
        Verifies provided hash against any authorized founder hash using constant-time compare.
        """
        if not provided_hash:
            return False
        for ah in self.cfg.authorized_hashes:
            if hmac.compare_digest(provided_hash, ah):
                return True
        return False

    def can_modify_system(self, provided_hash: str, action: str = "unspecified") -> bool:
        """
        Returns True if the caller is authorized AND not under lockdown.
        Tracks failures and may trigger lockdown.
        """
        now = _now()
        self._sweep_failures(now)

        # If already locked and cooldown not expired -> deny
        if self.lockdown.active and self._lockdown_active(now):
            self._log("SystemSanctity", "modify_attempt_during_lockdown", "BLOCKED", {"action": action})
            return False

        # Verify
        if self.verify_founder_hash(provided_hash):
            self._log("SystemSanctity", "modify_allowed", "OK", {"action": action})
            # successful auth also clears stale failures
            self._sweep_failures(now, clear_all=True)
            # if in cooldown but founder is verified, we still keep lockdown until manual reset
            return True

        # Failed verification
        self._failures.append(now)
        self.last_breach_at = now
        self._log("SystemSanctity", "modify_denied", "BLOCKED", {"action": action})

        # Evaluate for lockdown
        if self._failure_count(now) >= self.cfg.max_failures:
            self._enter_lockdown("Multiple failed founder verifications", now)
        return False

    # ---------- Manual control ----------

    def reset_lockdown(self, founder_hash: str, reason: str = "manual_release") -> bool:
        """
        Founder-confirmed manual release from lockdown.
        """
        if not self.verify_founder_hash(founder_hash):
            self._log("SystemSanctity", "reset_lockdown_failed", "BLOCKED", {"reason": "invalid_founder_hash"})
            return False

        self.lockdown = LockdownState(active=False)
        self._log("SystemSanctity", "reset_lockdown", "OK", {"reason": reason})
        return True

    # ---------- Introspection ----------

    def status(self) -> dict:
        return {
            "lockdown": self.lockdown.as_dict(),
            "last_breach_at": self.last_breach_at.isoformat() if self.last_breach_at else None,
            "failures_in_window": self._failure_count(_now()),
            "config": {
                "window_seconds": int(self.cfg.window.total_seconds()),
                "max_failures": self.cfg.max_failures,
                "cooldown_seconds": int(self.cfg.cooldown.total_seconds()),
            },
        }

    # ---------- Internals ----------

    def _sweep_failures(self, now: datetime, clear_all: bool = False) -> None:
        if clear_all:
            self._failures.clear()
            return
        cutoff = now - self.cfg.window
        while self._failures and self._failures[0] < cutoff:
            self._failures.popleft()

    def _failure_count(self, now: datetime) -> int:
        self._sweep_failures(now)
        return len(self._failures)

    def _enter_lockdown(self, reason: str, now: datetime) -> None:
        if not self.lockdown.active:
            self.lockdown = LockdownState(active=True, since=now, reason=reason)
            self._alert("⚠️ SYSTEM LOCKDOWN", reason)
            self._log("SystemSanctity", "lockdown_enter", "BLOCKED", {"reason": reason})

    def _lockdown_active(self, now: datetime) -> bool:
        if not self.lockdown.active or not self.lockdown.since:
            return False
        # Auto-release after cooldown (manual override recommended for high-assurance ops)
        if now - self.lockdown.since >= self.cfg.cooldown:
            # Do not auto-release silently—keep it active until founder resets
            return True
        return True

    # ---------- hooks ----------

    def _alert(self, subject: str, body: str) -> None:
        if self.on_alert:
            try:
                self.on_alert(subject, body)
            except Exception:
                pass  # keep guardrail resilient

    def _log(self, module: str, action: str, status: str, meta: Optional[dict] = None) -> None:
        if self.on_log:
            try:
                self.on_log(module, action, status, meta or {})
            except Exception:
                pass


# ---------- Example usage ----------
if __name__ == "__main__":
    # Demo alert/log hooks
    def demo_alert(subject: str, body: str):
        print(f"[ALERT] {subject}: {body}")

    def demo_log(module: str, action: str, status: str, meta: dict):
        print(f"[LOG] {module} :: {action} -> {status} | {meta}")

    sanct = SystemSanctity(on_alert=demo_alert, on_log=demo_log)

    # Fail a few times
    for _ in range(5):
        print("can_modify?", sanct.can_modify_system("bad.hash", action="edit_memory"))

    print("STATUS:", sanct.status())

    # Proper founder reset (replace with real hash)
    print("Reset lockdown:", sanct.reset_lockdown("husnain.ali.dna.hash"))

    # Now authorized
    print("can_modify?", sanct.can_modify_system("husnain.ali.dna.hash", action="edit_memory"))
    print("STATUS:", sanct.status())
