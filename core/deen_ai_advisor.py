# core/deen_ai_advisor.py
# HAIL — DeenAIAdvisor (Upgraded)
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional

from core.deen_suggestion_generator import DeenSuggestionGenerator
from core.quran_filter import QuranFilter
from core.shariah_guard import ShariahGuard

try:
    from core.action_logger import ActionLogger
except Exception:  # pragma: no cover
    ActionLogger = None  # type: ignore


@dataclass
class AdviceResult:
    status: str                   # "advice_ready" | "blocked" | "error"
    original_query: str
    identified_issue: Optional[str] = None
    suggestion: Dict[str, Any] = field(default_factory=dict)
    quran_validation: Dict[str, Any] = field(default_factory=dict)
    shariah_validation: Dict[str, Any] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DeenAIAdvisor:
    """
    Main advisory orchestrator:
      1) Detect issue (keywords; can be upgraded to NLP later)
      2) Generate suggestion via DeenSuggestionGenerator
      3) Validate via Qur’anFilter and ShariahGuard (Shari’ah-first)
      4) Return structured advice, with optional ActionLogger / MissionLog sinks
    """

    _ISSUE_KEYWORDS = {
        "anger": ["angry", "furious", "mad", "rage", "irritated"],
        "depression": ["depressed", "hopeless", "very sad", "worthless", "empty"],
        "anxiety": ["anxious", "panic", "nervous", "worry"],
        "laziness": ["lazy", "unmotivated", "tired", "procrastinating"],
        "missed_fajr": ["missed fajr", "couldn't wake", "missed prayer", "overslept fajr"],
        "distracted": ["can't focus", "distracted", "mind wandering"],
    }

    def __init__(
        self,
        *,
        suggester: Optional[DeenSuggestionGenerator] = None,
        quran_filter: Optional[QuranFilter] = None,
        shariah_guard: Optional[ShariahGuard] = None,
        action_logger: Optional["ActionLogger"] = None,
        mission_log_sink: Optional[callable] = None,  # lambda d: mission_log.append(...)
    ) -> None:
        self.suggester = suggester or DeenSuggestionGenerator()
        self.quran_filter = quran_filter or QuranFilter()
        self.shariah_guard = shariah_guard or ShariahGuard()
        self.log = action_logger
        self.mission_log_sink = mission_log_sink

    # -------- public API --------

    def advise(self, user_query: str, *, context: Optional[Dict[str, Any]] = None, actor_id: Optional[str] = None, source: Optional[str] = None) -> Dict[str, Any]:
        if not user_query or not user_query.strip():
            res = AdviceResult(status="error", original_query=user_query or "", notes=["Empty query"])
            self._write_logs(res, actor_id, source)
            return res.to_dict()

        ctx = context or {}
        issue = self.detect_issue(user_query)

        # Generate suggestion (always safe text; the guard will enforce rules)
        suggestion = self.suggester.suggest(issue) if issue else {
            "status": "neutral",
            "message": "No specific issue detected. Share more context (time, feelings, goal)."
        }

        # Qur’an + Shari’ah validations
        quran_check = self.quran_filter.check_text(user_query)
        shariah_check = self.shariah_guard.validate_action(user_query)

        # Shari’ah-first: if ShariahGuard blocks, we do not pass the suggestion through
        if isinstance(shariah_check, dict) and not shariah_check.get("allowed", True):
            res = AdviceResult(
                status="blocked",
                original_query=user_query,
                identified_issue=issue,
                suggestion={"status": "blocked", "message": "Advice blocked by Shari’ah rules."},
                quran_validation=quran_check if isinstance(quran_check, dict) else {"result": quran_check},
                shariah_validation=shariah_check,
                notes=["Shari’ah guard denial"],
            )
            self._write_logs(res, actor_id, source)
            return res.to_dict()

        # If Qur’an filter reports a problem, downgrade to cautionary advice
        notes: List[str] = []
        if isinstance(quran_check, dict) and not quran_check.get("allowed", True):
            notes.append("Qur’an filter raised caution")
            if isinstance(suggestion, dict):
                suggestion = {
                    **suggestion,
                    "status": "caution",
                    "message": f"{suggestion.get('message','')}\n\nNote: Qur’an alignment requires caution."
                }

        res = AdviceResult(
            status="advice_ready",
            original_query=user_query,
            identified_issue=issue,
            suggestion=suggestion if isinstance(suggestion, dict) else {"status": "ok", "message": str(suggestion)},
            quran_validation=quran_check if isinstance(quran_check, dict) else {"result": quran_check},
            shariah_validation=shariah_check if isinstance(shariah_check, dict) else {"result": shariah_check},
            notes=notes,
        )
        self._write_logs(res, actor_id, source, context=ctx)
        return res.to_dict()

    def detect_issue(self, text: str) -> Optional[str]:
        t = text.lower()
        for issue, keys in self._ISSUE_KEYWORDS.items():
            if any(k in t for k in keys):
                return issue
        return None

    # -------- sinks --------

    def _write_logs(self, res: AdviceResult, actor_id: Optional[str], source: Optional[str], *, context: Optional[Dict[str, Any]] = None) -> None:
        # ActionLogger
        if self.log:
            try:
                decision = "APPROVED" if res.status == "advice_ready" else ("DENIED" if res.status == "blocked" else "INFO")
                self.log.log(
                    action_type="Advice",
                    decision=decision,
                    module="deen_ai_advisor",
                    status="Success" if res.status == "advice_ready" else ("Failure" if res.status == "blocked" else "Success"),
                    user_input=res.original_query,
                    actor_id=actor_id,
                    source=source or "advisor",
                    reason=res.suggestion.get("message", "")[:300],
                    context={"issue": res.identified_issue, "status": res.status, **(context or {})},
                    meta={"notes": res.notes},
                )
            except Exception:
                pass

        # MissionLog (optional)
        if self.mission_log_sink:
            try:
                verdict = "halal" if res.status == "advice_ready" else ("haram" if res.status == "blocked" else "shubha")
                score = 0.08 if res.status == "advice_ready" else (0.8 if res.status == "blocked" else 0.4)
                self.mission_log_sink({
                    "actor_id": actor_id or "user",
                    "activity": "deen_advice",
                    "verdict": verdict,
                    "score": score,
                    "reasons": [res.suggestion.get("message","")[:120]],
                    "tags": ["advice", res.identified_issue or "general"],
                    "payload": res.to_dict(),
                })
            except Exception:
                pass


# Example quick test
if __name__ == "__main__":
    advisor = DeenAIAdvisor(action_logger=ActionLogger(also_print=True) if ActionLogger else None)
    print(advisor.advise("I missed Fajr and feel very sad", actor_id="husnain_ali", source="cli"))
