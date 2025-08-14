# core/violation_handler.py
# Phase 3 — Shari'ah Violation Handling
# - Scans input via QuranicViolationDetector
# - Blocks on violation, logs to optional Mission Log (Phase 3.51)
# - Optionally emits trust violations + encrypted audit logs
# - Compact, typed response payloads

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

from core.quranic_violation_detector import QuranicViolationDetector

# Optional imports (fail-quiet if not present in the build)
try:
    from core.deen_mission_log import DeenMissionLog, Verdict
except Exception:
    DeenMissionLog = None  # type: ignore
    Verdict = None         # type: ignore

try:
    from core.secure_logger import SecureLogger
except Exception:
    SecureLogger = None  # type: ignore

try:
    from core.trust_violation_detector import TrustViolationDetector, Category, Severity
except Exception:
    TrustViolationDetector = None  # type: ignore
    Category = None                # type: ignore
    Severity = None                # type: ignore


@dataclass
class ViolationDecision:
    status: str                  # "blocked" | "allowed"
    message: str
    matched_terms: List[str]
    source: str
    timestamp: str
    action: Optional[str] = None    # e.g., "Blocked & Logged"
    log_ref: Optional[str] = None   # mission log entry_id if available

    def to_dict(self) -> Dict:
        return asdict(self)


class ViolationHandler:
    def __init__(self,
                 mission_log: Optional["DeenMissionLog"] = None,
                 secure_logger: Optional["SecureLogger"] = None,
                 trust_detector: Optional["TrustViolationDetector"] = None):
        self.detector = QuranicViolationDetector()
        self.mission_log = mission_log
        self.secure_logger = secure_logger
        self.trust_detector = trust_detector

    # ---------- public API ----------
    def handle_input(self, user_input: str, source: str = "unknown") -> Dict:
        ts = datetime.now(timezone.utc).isoformat()
        result = self.detector.detect_violation(user_input)

        # No violation → allow
        if not result.get("violation"):
            decision = ViolationDecision(
                status="allowed",
                message="Input accepted. No Shari'ah violations found.",
                matched_terms=[],
                source=source,
                timestamp=ts
            )
            self._audit("ViolationHandler", "allow_input", "ALLOWED", {
                "source": source,
                "text_len": len(user_input)
            })
            return decision.to_dict()

        # Violation → block, log, trust signal
        matched = list(result.get("matched_terms", []))
        decision = ViolationDecision(
            status="blocked",
            message="Action denied due to Shari'ah violation.",
            matched_terms=matched,
            source=source,
            timestamp=ts,
            action="Blocked & Logged"
        )

        # 1) Mission Log (if available)
        if self.mission_log and Verdict:
            entry = self.mission_log.append(
                actor_id=source,
                activity="input_violation",
                verdict=Verdict.HARAM,
                score=0.95,
                reasons=[f"Matched prohibited terms: {', '.join(matched)}"],
                tags=["violation", "quranic", "blocked"],
                payload={"input_preview": user_input[:160], "matched_terms": matched}
            )
            decision.log_ref = getattr(entry, "entry_id", None)

        # 2) Trust Violation signal (if module available)
        if self.trust_detector and Category and Severity:
            self.trust_detector.detect_violation(
                Category.UNVERIFIED_COMMAND,
                detail=f"Blocked Shari'ah violation from {source}: {', '.join(matched)}",
                severity=Severity.HIGH
            )

        # 3) Encrypted audit line (if SecureLogger present)
        self._audit("ViolationHandler", "block_input", "BLOCKED", {
            "source": source,
            "matched": matched,
            "preview": user_input[:120]
        })

        return decision.to_dict()

    def get_action_log(self) -> List[Dict]:
        """
        Backwards-compat shim (we now rely on MissionLog/SecureLogger).
        Returns empty list by design.
        """
        return []

    # ---------- internals ----------
    def _audit(self, module: str, action: str, status: str, meta: Optional[Dict] = None) -> None:
        if not self.secure_logger:
            return
        try:
            self.secure_logger.log(module=module, action=action, status=status, metadata=meta or {})
        except Exception:
            # Never raise from auditing
            pass


# ---------------- quick self-test ----------------
if __name__ == "__main__":
    # Runs without optional deps
    vh = ViolationHandler()
    print(vh.handle_input("Please invest with riba interest account", source="cli"))
    print(vh.handle_input("Schedule Fajr prayer reminder", source="cli"))
