# core/action_verification_log.py
# Tracks verified vs unverified actions with structured entries and optional sinks.

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from collections import deque
from threading import RLock
from typing import Any, Deque, Dict, Iterable, Optional

try:
    # Optional: only used if provided by caller
    from core.action_logger import ActionLogger
except Exception:  # pragma: no cover
    ActionLogger = None  # type: ignore


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class VerificationEntry:
    timestamp: str
    action: str
    initiator: str
    verified: bool
    verification_source: str
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ActionVerificationLog:
    """
    Thread-safe, bounded in-memory verification log with optional sinks:
      - action_logger (JSONL)
      - mission_log_sink (callable taking a dict)
    """

    def __init__(
        self,
        *,
        max_entries: int = 2000,
        action_logger: Optional["ActionLogger"] = None,
        mission_log_sink: Optional[callable] = None,  # e.g., lambda d: mission_log.append(...)
        also_print: bool = False,
    ) -> None:
        self._verified: Deque[VerificationEntry] = deque(maxlen=max_entries)
        self._unverified: Deque[VerificationEntry] = deque(maxlen=max_entries)
        self._lock = RLock()
        self._logger = action_logger
        self._mission_log_sink = mission_log_sink
        self._also_print = also_print

    # -------- core API

    def log_action(
        self,
        action_name: str,
        initiator: str,
        verified: bool,
        verification_source: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> VerificationEntry:
        entry = VerificationEntry(
            timestamp=_utc_iso(),
            action=action_name,
            initiator=initiator,
            verified=verified,
            verification_source=verification_source,
            metadata=metadata or {},
        )
        with self._lock:
            if verified:
                self._verified.append(entry)
            else:
                self._unverified.append(entry)

        # side effects (optional sinks)
        if self._logger:
            try:
                decision = "APPROVED" if verified else "DENIED"
                self._logger.log(
                    action_type="Verification",
                    decision=decision,
                    module="action_verification_log",
                    status="Success",
                    user_input=None,
                    actor_id=initiator,
                    source=verification_source,
                    reason=entry.metadata.get("reason"),
                    context={"action": action_name},
                    meta={"verified": verified},
                )
            except Exception:
                pass  # never block

        if self._mission_log_sink:
            try:
                # Expecting a callable like: lambda d: mission_log.append(...)
                self._mission_log_sink(
                    {
                        "actor_id": initiator,
                        "activity": "action_verification",
                        "verdict": "halal" if verified else "shubha",
                        "score": 0.01 if verified else 0.6,
                        "reasons": [entry.metadata.get("reason", "verified" if verified else "unverified")],
                        "tags": ["verification", verification_source],
                        "payload": entry.to_dict(),
                    }
                )
            except Exception:
                pass

        if self._also_print:
            print(f"[VERIFICATION] {action_name} by {initiator} -> {'VERIFIED' if verified else 'UNVERIFIED'}")

        return entry

    def verify_and_log(
        self,
        *,
        check_passed: bool,
        action_name: str,
        initiator: str,
        verification_source: str,
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Helper: record verification result and return the boolean outcome.
        """
        md = dict(metadata or {})
        if reason:
            md["reason"] = reason
        self.log_action(
            action_name=action_name,
            initiator=initiator,
            verified=check_passed,
            verification_source=verification_source,
            metadata=md,
        )
        return check_passed

    # -------- queries

    def get_verified_actions(self) -> Iterable[Dict[str, Any]]:
        with self._lock:
            return [e.to_dict() for e in list(self._verified)]

    def get_unverified_attempts(self) -> Iterable[Dict[str, Any]]:
        with self._lock:
            return [e.to_dict() for e in list(self._unverified)]

    def get_last_action_status(self) -> Dict[str, Any] | str:
        with self._lock:
            if self._verified:
                return self._verified[-1].to_dict()
            if self._unverified:
                return self._unverified[-1].to_dict()
        return "No actions logged yet."

    def reset_logs(self) -> None:
        with self._lock:
            self._verified.clear()
            self._unverified.clear()
