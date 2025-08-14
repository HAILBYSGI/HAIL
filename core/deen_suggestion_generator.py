# core/deen_suggestion_generator.py
# HAIL — DeenSuggestionGenerator (Upgraded)
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional, Sequence
import random

try:
    from core.action_logger import ActionLogger
except Exception:  # pragma: no cover
    ActionLogger = None  # type: ignore


@dataclass
class SuggestionResult:
    status: str                              # "suggestions_found" | "no_suggestion_found"
    issue: Optional[str] = None
    suggestions: List[str] = field(default_factory=list)
    note: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DeenSuggestionGenerator:
    """
    Provides deen-aligned behavioral suggestions for common issues.
    - Synonym matching for robust detection
    - Deterministic + random mixing (to avoid repetition fatigue)
    - Optional sinks: ActionLogger + Mission Log
    """

    _CANONICAL: Dict[str, List[str]] = {
        "anger": [
            "Make wuḍū to cool anger (Sunnah).",
            "Say: A‘ūdhu billāhi min ash‑shayṭān ir‑rajīm.",
            "Change posture: sit if standing, lie down if sitting.",
            "Keep silent; walk away for 2 minutes, then return calmly.",
        ],
        "depression": [
            "Increase dhikr; repeat Ḥasbunallāhu wa ni‘mal‑wakīl with focus.",
            "Recite Sūrah Ad‑Ḍuḥā; reflect on Allah’s favors upon you.",
            "Keep ṣalāh on time; it restrains from shameful/unjust deeds (29:45).",
            "Write 3 gratitude items and make sincere du‘ā of hope.",
        ],
        "laziness": [
            "Make the du‘ā: “Allāhumma innī a‘ūdhu bika minal‑‘ajzi wal‑kasal …”.",
            "Split the task into the smallest next action and begin with Bismillāh.",
            "Stand up, do quick wuḍū, then 2 rak‘ah of intention and start.",
        ],
        "missed_fajr": [
            "Sleep early; avoid screens in the last 60 minutes before bed.",
            "Set two alarms and request a family member’s wake‑up assist.",
            "Before sleep, make du‘ā to be among those who establish Fajr.",
            "If missed, pray immediately upon waking and review sleep routine.",
        ],
        # Add more canonical topics as you expand the system:
        "stress": [
            "Recite: ألا بذكرِ اللهِ تطمئنُّ القلوب (13:28) and do 10 deep breaths.",
            "Take a 5‑minute walk while doing tasbīḥ quietly.",
        ],
    }

    _SYNONYMS: Dict[str, Sequence[str]] = {
        "anger": ["angry", "furious", "rage", "mad", "irritated"],
        "depression": ["depressed", "hopeless", "down", "empty", "very sad"],
        "laziness": ["lazy", "unmotivated", "procrastinate", "no energy"],
        "missed_fajr": ["missed fajr", "overslept fajr", "couldn't wake", "late fajr"],
        "stress": ["stressed", "anxious", "pressure"],
    }

    def __init__(
        self,
        *,
        action_logger: Optional["ActionLogger"] = None,
        mission_log_sink: Optional[callable] = None,  # lambda payload: mission_log.append(...)
        seed: Optional[int] = None,
    ) -> None:
        self.log = action_logger
        self.mission_log_sink = mission_log_sink
        self.rand = random.Random(seed)

    # --------------- Public API ---------------

    def suggest(self, issue: str, *, limit: int = 3, shuffle: bool = True) -> Dict[str, Any]:
        """
        Returns up to `limit` deen suggestions for the canonical issue (or synonym).
        """
        canonical = self._canonicalize(issue)
        items = list(self._CANONICAL.get(canonical, []))

        if not items:
            res = SuggestionResult(
                status="no_suggestion_found",
                issue=canonical or issue,
                note="No predefined suggestions; consider adding to knowledge base.",
            )
            self._sinks(res, source_issue=issue)
            return res.to_dict()

        if shuffle:
            self.rand.shuffle(items)

        picked = items[: max(1, int(limit))]
        res = SuggestionResult(
            status="suggestions_found",
            issue=canonical,
            suggestions=picked,
        )
        self._sinks(res, source_issue=issue)
        return res.to_dict()

    # --------------- Helpers ---------------

    def _canonicalize(self, raw: str) -> str:
        t = (raw or "").strip().lower()
        if not t:
            return ""
        # direct hit
        if t in self._CANONICAL:
            return t
        # synonym hit
        for canon, keys in self._SYNONYMS.items():
            if any(k in t for k in keys):
                return canon
        return t  # fallback: unknown label; caller will get "no_suggestion_found"

    # --------------- Sinks ---------------

    def _sinks(self, res: SuggestionResult, *, source_issue: str) -> None:
        # Action log (optional)
        if self.log:
            try:
                self.log.log(
                    action_type="Suggestion",
                    decision="APPROVED" if res.status == "suggestions_found" else "INFO",
                    module="deen_suggestion_generator",
                    status="Success",
                    reason=(res.suggestions[0] if res.suggestions else res.note or "No suggestions"),
                    context={"issue": res.issue or source_issue, "count": len(res.suggestions)},
                    meta={"picked": res.suggestions},
                )
            except Exception:
                pass

        # Mission Log (optional)
        if self.mission_log_sink:
            try:
                self.mission_log_sink(
                    {
                        "actor_id": "user",
                        "activity": "deen_suggestion",
                        "verdict": "halal",
                        "score": 0.05,
                        "reasons": [res.suggestions[0][:120]] if res.suggestions else ["no suggestions"],
                        "tags": ["advice", res.issue or "unknown"],
                        "payload": res.to_dict(),
                    }
                )
            except Exception:
                pass


# --------------- Example quick test ---------------
if __name__ == "__main__":
    logger = ActionLogger(also_print=True) if ActionLogger else None  # type: ignore
    gen = DeenSuggestionGenerator(action_logger=logger, seed=42)
    print(gen.suggest("I'm very angry", limit=2))
    print(gen.suggest("missed fajr today", limit=3))
    print(gen.suggest("new unknown topic"))
