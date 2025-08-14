# core/command_handler.py
# Part of HAIL Phase 3 – AI Ethics, Command & Security Logic (Upgraded)

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, Optional

from core.intent_classifier import IntentClassifier
from core.shariah_guard import ShariahGuard
from core.halal_task_router import HalalTaskRouter
from core.action_blocker import ActionBlocker
from core.action_logger import ActionLogger


@dataclass
class CommandResult:
    status: str                      # "ready" | "rejected" | "error"
    intent: str
    reason: str = ""
    routed_to: Optional[str] = None
    confidence: Optional[float] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CommandHandler:
    """
    Orchestrates a single user command:
      1) Classify intent
      2) Shari'ah-first guard (ActionBlocker + ShariahGuard)
      3) Route to halal task router
      4) Log decisions & outcomes
    """

    def __init__(
        self,
        *,
        classifier: Optional[IntentClassifier] = None,
        shariah_guard: Optional[ShariahGuard] = None,
        task_router: Optional[HalalTaskRouter] = None,
        blocker: Optional[ActionBlocker] = None,
        logger: Optional[ActionLogger] = None,
    ) -> None:
        self.classifier = classifier or IntentClassifier()
        self.shariah_guard = shariah_guard or ShariahGuard()
        self.task_router = task_router or HalalTaskRouter()
        self.blocker = blocker or ActionBlocker()
        self.log = logger or ActionLogger()

    def handle_command(
        self,
        user_command: str,
        *,
        actor_id: Optional[str] = None,
        source: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        ctx = context or {}

        # 1) Classify
        intent = self.classifier.classify(user_command)

        # 2) Shari'ah-first guard (ActionBlocker) – covers phase + policy
        decision = self.blocker.should_block(
            user_command, actor_id=actor_id, source=source, context=ctx
        )
        self.log.log_decision(decision, module="command_handler", action_type="CommandDecision")
        if decision.get("block"):
            res = CommandResult(
                status="rejected",
                intent=intent,
                reason=decision.get("reason", "Not compliant"),
                meta={"code": decision.get("code"), **decision.get("meta", {})},
            )
            self.log.log(
                action_type="Command",
                decision="BLOCKED",
                module="command_handler",
                status="Failure",
                user_input=user_command,
                actor_id=actor_id,
                source=source,
                reason=res.reason,
                context={"intent": intent},
                meta=res.meta,
            )
            return res.to_dict()

        # Extra belt-and-suspenders check using ShariahGuard (keeps compatibility)
        if not self.shariah_guard.is_halal(user_command):
            res = CommandResult(
                status="rejected",
                intent=intent,
                reason="Command not compliant with Islamic principles.",
            )
            self.log.log(
                action_type="Command",
                decision="BLOCKED",
                module="shariah_guard",
                status="Failure",
                user_input=user_command,
                actor_id=actor_id,
                source=source,
                reason=res.reason,
                context={"intent": intent},
            )
            return res.to_dict()

        # 3) Route to halal task router
        try:
            task_result = self.task_router.route_task(user_command)
            if task_result.get("status") == "accepted":
                res = CommandResult(
                    status="ready",
                    intent=intent,
                    routed_to=task_result.get("routed_to"),
                    confidence=task_result.get("confidence"),
                    reason="Routed successfully",
                )
                self.log.log(
                    action_type="Command",
                    decision="APPROVED",
                    module=res.routed_to or "halal_task_router",
                    status="Success",
                    user_input=user_command,
                    actor_id=actor_id,
                    source=source,
                    reason=res.reason,
                    context={"intent": intent},
                )
                return res.to_dict()

            # not accepted
            res = CommandResult(
                status="rejected",
                intent=intent,
                reason=task_result.get("reason", "Unable to route command"),
            )
            self.log.log(
                action_type="Command",
                decision="DENIED",
                module="halal_task_router",
                status="Failure",
                user_input=user_command,
                actor_id=actor_id,
                source=source,
                reason=res.reason,
                context={"intent": intent},
            )
            return res.to_dict()

        except Exception as e:
            # 4) Safety net
            res = CommandResult(
                status="error",
                intent=intent,
                reason=f"{type(e).__name__}: {e}",
            )
            self.log.log_exception(module="command_handler", err=e, where="route_task", context={"intent": intent})
            return res.to_dict()


# Example usage
if __name__ == "__main__":
    ch = CommandHandler()
    print(ch.handle_command("Send reminder for Fajr salah", actor_id="husnain_ali", source="cli"))
