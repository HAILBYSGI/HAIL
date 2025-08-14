# core/halal_task_router.py
# HAIL — HalalTaskRouter (Upgraded)
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional, Tuple

# Core dependencies (existing HAIL modules)
from core.shariah_guard import ShariahGuard
from core.intent_classifier import IntentClassifier
from core.query_matcher import QueryMatcher

# Optional observability sinks (best‑effort; no hard dependency)
try:
    from core.action_logger import ActionLogger  # type: ignore
except Exception:  # pragma: no cover
    ActionLogger = None  # type: ignore

try:
    # If present, we can emit a normalized event for visibility
    from core.deen_activity_monitor import (
        DeenActivityMonitor, ActivityEvent, ActivityType, Verdict as MonitorVerdict
    )  # type: ignore
except Exception:  # pragma: no cover
    DeenActivityMonitor = None  # type: ignore
    ActivityEvent = None  # type: ignore
    ActivityType = None  # type: ignore
    MonitorVerdict = None  # type: ignore


@dataclass
class RouteResult:
    status: str                 # "accepted" | "rejected" | "escalate"
    routed_to: Optional[str]    # system/phase target for accepted/escalate
    intent: str                 # detected intent label
    confidence: float           # 0..1
    reason: str                 # human-readable reason
    risk: Optional[float] = None
    tags: Optional[list] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class HalalTaskRouter:
    """
    Routes user tasks to halal systems with guardrails.
    - Shari'ah filter gate (hard deny on violation)
    - Intent classification + query/phase matching
    - Confidence thresholds with escalation path
    - Optional activity emission to DeenActivityMonitor
    - Optional sinks to ActionLogger / Mission Log
    """

    # Confidence thresholds
    HIGH = 0.80
    LOW = 0.40

    def __init__(
        self,
        *,
        mission_log_sink: Optional[callable] = None,     # lambda payload: mission_log.append(...)
        activity_monitor: Optional[Any] = None,          # pass a DeenActivityMonitor instance if available
    ) -> None:
        self.shariah_guard = ShariahGuard()
        self.intent_classifier = IntentClassifier()
        self.query_matcher = QueryMatcher()

        self._mission_log_sink = mission_log_sink
        self._monitor = activity_monitor if activity_monitor is not None else (DeenActivityMonitor() if DeenActivityMonitor else None)
        self._action_logger = ActionLogger() if ActionLogger else None

        # Simple intent->preferred target mapping (override/extend as needed)
        self._routes = {
            "automation": "AutoAmanahEngine",
            "ibadah": "IbadahTracker",
            "dua": "DuaResponseEngine",
            "zakat": "ZakatModule",
            "investment": "HalalInvestmentSystem",
            "family": "FamilyAlignmentCore",
            "workflow": "IslamicWorkflowEngine",
            "therapy": "QuranTherapyModule",
            "wellness": "WellnessMonitor",
            "daily": "HalalCompanion",
        }

    # -------------- Public API --------------

    def route_task(self, task_description: str) -> Dict[str, Any]:
        text = (task_description or "").strip()
        if not text:
            return RouteResult(
                status="rejected",
                routed_to=None,
                intent="unknown",
                confidence=0.0,
                reason="Empty task description.",
                tags=["empty"],
            ).to_dict()

        # 1) Shari'ah gate (hard deny)
        if not self.shariah_guard.is_halal(text):
            result = RouteResult(
                status="rejected",
                routed_to=None,
                intent="blocked",
                confidence=1.0,
                reason="Task rejected — not Shari’ah‑compliant.",
                tags=["haram", "blocked"],
            )
            self._observe(text, result)
            self._emit_activity(text, verdict="haram", tags=["task", "blocked"])
            return result.to_dict()

        # 2) Intent classification
        intent = self.intent_classifier.classify(text)
        intent = (intent or "unknown").lower()

        # 3) System/phase matching
        match_score, system = self._safe_match(text)  # (0..1, system_name_or_none)

        # Prefer a canonical route if we have a known mapping for the intent
        preferred = self._routes.get(intent)
        target = preferred or system

        # 4) Decide final action based on confidence tiers
        if match_score >= self.HIGH and target:
            result = RouteResult(
                status="accepted",
                routed_to=target,
                intent=intent,
                confidence=float(match_score),
                reason=f"High confidence route to {target}.",
                tags=["accepted", "high-confidence"],
            )
        elif match_score >= self.LOW and target:
            result = RouteResult(
                status="escalate",
                routed_to=target,
                intent=intent,
                confidence=float(match_score),
                reason="Moderate confidence — escalate for human/founder confirmation.",
                tags=["escalate", "moderate-confidence"],
            )
        else:
            result = RouteResult(
                status="escalate",
                routed_to="ManualReview",
                intent=intent,
                confidence=float(match_score),
                reason="Low confidence — route to ManualReview.",
                tags=["escalate", "low-confidence"],
            )

        self._observe(text, result)
        self._emit_activity(text, verdict="halal", tags=["task", result.status])
        return result.to_dict()

    # -------------- Internals --------------

    def _safe_match(self, text: str) -> Tuple[float, Optional[str]]:
        try:
            score, system = self.query_matcher.match(text)
            score = float(score or 0.0)
            system = str(system) if system else None
            return max(0.0, min(1.0, score)), system
        except Exception:
            return 0.0, None

    def _observe(self, text: str, result: RouteResult) -> None:
        # ActionLogger
        if self._action_logger:
            try:
                self._action_logger.log(
                    action_type="HalalTaskRouter",
                    user_input=text[:200],
                    system_decision=result.status.upper(),
                    module="halal_task_router",
                    reason=result.reason[:300],
                    status="Success",
                )
            except Exception:
                pass

        # Mission Log
        if self._mission_log_sink:
            try:
                self._mission_log_sink({
                    "actor_id": "user",  # replace if you have a real id in context
                    "activity": "task_route",
                    "verdict": "halal",
                    "score": 0.10 if result.status == "accepted" else 0.30,
                    "reasons": [result.reason],
                    "tags": result.tags or [],
                    "payload": {
                        "intent": result.intent,
                        "confidence": result.confidence,
                        "routed_to": result.routed_to,
                    },
                })
            except Exception:
                pass

    def _emit_activity(self, text: str, *, verdict: str, tags: list) -> None:
        """
        Emit a lightweight event into DeenActivityMonitor (if available)
        so it can contribute to EWMA/surge and risk metrics.
        """
        if not (self._monitor and ActivityEvent and ActivityType):
            return
        try:
            ev = ActivityEvent.new(
                actor_id="user",  # swap with real actor id if available
                activity=ActivityType.SYSTEM_EVENT,
                payload={"title": "task_route_request", "text": text[:300]},
                tags=tags,
            )
            self._monitor.emit(ev)
        except Exception:
            pass
