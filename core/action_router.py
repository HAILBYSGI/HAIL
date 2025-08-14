# core/action_router.py
# Routes classified user intent to the appropriate HAIL execution module
from __future__ import annotations

from typing import Dict, Optional, Any, Tuple

from core.intent_classifier import IntentClassifier
from core.modules import (
    AutoAmanahEngine,
    IbadahTracker,
    DuaResponseEngine,
    ZakatModule,
    HalalInvestmentSystem,
    FamilyAlignmentCore,
    IslamicWorkflowEngine,
    QuranTherapyModule,
    HalalCompanion,
    WellnessMonitor,
)
from core.action_blocker import ActionBlocker
from core.action_logger import ActionLogger


class ActionRouter:
    """
    Central router for user requests.
    Order of operations:
      1) Classify intent
      2) Shari'ah-first guard (ActionBlocker)
      3) Route to selected module
      4) Log decision/result
    """

    def __init__(
        self,
        *,
        classifier: Optional[IntentClassifier] = None,
        blocker: Optional[ActionBlocker] = None,
        logger: Optional[ActionLogger] = None,
    ) -> None:
        self.classifier = classifier or IntentClassifier()
        self.blocker = blocker or ActionBlocker()
        self.log = logger or ActionLogger()

        # Initialize system modules
        self.modules: Dict[str, Any] = {
            "Auto-Amanah Engine": AutoAmanahEngine(),
            "Ibadah Tracker": IbadahTracker(),
            "Dua Response Engine": DuaResponseEngine(),
            "Zakat Module": ZakatModule(),
            "Halal Investment System": HalalInvestmentSystem(),
            "Family Alignment Core": FamilyAlignmentCore(),
            "Islamic Workflow Engine": IslamicWorkflowEngine(),
            "Qur’an-Based Therapy": QuranTherapyModule(),
            "Daily Halal Companion": HalalCompanion(),
            "Wellness Monitor": WellnessMonitor(),
        }

        # Provide a safe fallback if no module matches
        self.fallback_key = "Daily Halal Companion"

    def _suggest(self, intent_label: str) -> str:
        """Return a gentle suggestion when routing fails."""
        known = ", ".join(sorted(self.modules.keys()))
        return (
            "System: Unable to route your request. "
            "Detected intent: '{label}'. Please clarify or choose one of: {known}."
        ).format(label=intent_label or "unknown", known=known)

    def _pick_module(self, intent_label: str) -> Tuple[str, Any]:
        """Pick module by label or fallback."""
        if intent_label in self.modules:
            return intent_label, self.modules[intent_label]
        # Try simple heuristics (maps classifier aliases to canonical keys)
        alias_map = {
            "automation": "Auto-Amanah Engine",
            "ibadah": "Ibadah Tracker",
            "dua": "Dua Response Engine",
            "zakat": "Zakat Module",
            "investment": "Halal Investment System",
            "family": "Family Alignment Core",
            "workflow": "Islamic Workflow Engine",
            "therapy": "Qur’an-Based Therapy",
            "wellness": "Wellness Monitor",
            "daily": "Daily Halal Companion",
            "companion": "Daily Halal Companion",
        }
        key = alias_map.get(intent_label)
        if key and key in self.modules:
            return key, self.modules[key]
        # fallback
        return self.fallback_key, self.modules[self.fallback_key]

    def handle_request(
        self,
        user_input: str,
        *,
        actor_id: Optional[str] = None,
        source: Optional[str] = None,
        context: Optional[dict] = None,
    ) -> str:
        """
        Route a user_input to an appropriate module after Shari'ah validation.
        Returns module output (string). Logs classification, blocking, and result.
        """
        context = context or {}
        # 1) Classify
        intent_label = self.classifier.classify(user_input)

        # 2) Shari'ah-first guard (use ActionBlocker on raw command)
        decision = self.blocker.should_block(
            user_input, actor_id=actor_id, source=source, context=context
        )
        self.log.log_decision(decision, module="action_router", action_type="RoutingDecision")

        if decision.get("block"):
            msg = f"⚠️ Action blocked: {decision.get('reason', 'Not compliant')}"
            # Log final output
            self.log.log(
                action_type="Command",
                decision="BLOCKED",
                module="action_router",
                status="Failure",
                user_input=user_input,
                actor_id=actor_id,
                source=source,
                reason=decision.get("reason"),
                reasons=decision.get("reasons", []),
                context={"intent_label": intent_label},
                meta={"code": decision.get("code")},
            )
            return msg

        # 3) Route
        module_key, module = self._pick_module(intent_label)
        try:
            result = module.execute(user_input)
            outcome = "APPROVED"
            reason = f"Routed to {module_key}"
        except Exception as e:
            # If module fails, provide graceful message and log
            result = (
                "System: An error occurred while handling your request. "
                "Please try again or choose a different function."
            )
            outcome = "ERROR"
            reason = f"{type(e).__name__}: {e}"

        # 4) Log
        self.log.log(
            action_type="Command",
            decision=outcome,
            module=module_key if outcome == "APPROVED" else "action_router",
            status="Success" if outcome == "APPROVED" else "Failure",
            user_input=user_input,
            actor_id=actor_id,
            source=source,
            reason=reason,
            context={"intent_label": intent_label},
        )

        # If classifier label was unknown and we fell back, add suggestion text
        if module_key == self.fallback_key and intent_label not in self.modules:
            result = result + "\n\n" + self._suggest(intent_label)

        return result
