# core/action_blocker.py
# Part of HAIL Phase 3 – AI Ethics, Command & Security Logic

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from core.shariah_override import ShariahOverride
from core.phase_validator import PhaseValidator


@dataclass
class BlockDecision:
    block: bool
    reason: str
    reasons: List[str] = field(default_factory=list)
    code: str = "OK"  # e.g., SHARIAH_DENY, PHASE_INVALID, DENYLIST, ALLOWLIST, OK
    meta: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "block": self.block,
            "reason": self.reason,
            "reasons": self.reasons,
            "code": self.code,
            "meta": self.meta,
        }


class ActionBlocker:
    """
    Central gatekeeper for user/system commands.

    Ordering is intentional:
      1) Shari'ah compliance (cannot be bypassed)
      2) Blueprint phase validity
      3) Local allow/deny operational controls
    """

    def __init__(
        self,
        shariah: Optional[ShariahOverride] = None,
        phase_validator: Optional[PhaseValidator] = None,
        allowlist: Optional[List[str]] = None,
        denylist: Optional[List[str]] = None,
    ) -> None:
        self.shariah = shariah or ShariahOverride()
        self.phase_validator = phase_validator or PhaseValidator()
        # simple contains check; can be upgraded to patterns later
        self.allowlist = set(allowlist or [])
        self.denylist = set(denylist or [])

    def should_block(
        self,
        command: str,
        *,
        actor_id: Optional[str] = None,
        source: Optional[str] = None,
        context: Optional[Dict] = None,
    ) -> Dict:
        """
        Returns a decision dict for compatibility with callers.
        Use .to_dict() to keep a stable, explicit shape.
        """
        reasons: List[str] = []
        meta: Dict[str, str] = {}
        if actor_id:
            meta["actor_id"] = actor_id
        if source:
            meta["source"] = source

        # (0) Operational denylist check (lowest cost, early exit)
        if command in self.denylist:
            return BlockDecision(
                block=True,
                reason="Command is explicitly denied (operational policy).",
                reasons=["Matched denylist"],
                code="DENYLIST",
                meta=meta,
            ).to_dict()

        # (1) Shari'ah Compliance Check (always first, non-bypassable)
        shariah_result = self.shariah.evaluate_command(command, context=context or {})
        if not shariah_result.get("allowed", False):
            reasons.append(shariah_result.get("reason", "Not compliant with Shari'ah"))
            return BlockDecision(
                block=True,
                reason="Not compliant with Shari'ah.",
                reasons=reasons,
                code="SHARIAH_DENY",
                meta=meta,
            ).to_dict()

        # (2) Blueprint Phase Validity
        phase_result = self.phase_validator.is_valid_phase(command, context=context or {})
        if not phase_result.get("valid", False):
            reasons.append(phase_result.get("reason", "Invalid for current phase"))
            return BlockDecision(
                block=True,
                reason="Invalid for current HAIL blueprint phase.",
                reasons=reasons,
                code="PHASE_INVALID",
                meta=meta,
            ).to_dict()

        # (3) Operational allowlist (explicit allow, still AFTER Shari'ah and phase)
        if self.allowlist and command in self.allowlist:
            meta["allowlist"] = "hit"

        # All checks pass
        return BlockDecision(
            block=False,
            reason="Command is allowed.",
            reasons=reasons,
            code="OK",
            meta=meta,
        ).to_dict()


# Example usage
if __name__ == "__main__":
    blocker = ActionBlocker(allowlist=["Open halal article"], denylist=["Delete all logs"])
    print(blocker.should_block("Display non-halal content", actor_id="user123", source="cli"))
    print(blocker.should_block("Open halal article", actor_id="user123", source="cli"))
    print(blocker.should_block("Delete all logs", actor_id="user123", source="cli"))
