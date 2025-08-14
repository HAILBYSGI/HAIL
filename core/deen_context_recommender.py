# core/deen_context_recommender.py
# HAIL — DeenContextRecommender (Upgraded)
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional

from core.quran_filter import QuranFilter
from core.shariah_guard import ShariahGuard

try:
    from core.action_logger import ActionLogger
except Exception:  # pragma: no cover
    ActionLogger = None  # type: ignore


@dataclass
class DeenRecommendation:
    status: str                    # "success" | "blocked" | "error"
    context: str
    recommendation: Dict[str, str] = field(default_factory=dict)
    quran_validation: Dict[str, Any] = field(default_factory=dict)
    shariah_validation: Dict[str, Any] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DeenContextRecommender:
    """
    Given a user's emotional/situational context, recommend Islamic verses/actions.
    Pipeline:
      1) Match context using synonyms
      2) Produce Quran/Action suggestion
      3) Validate with QuranFilter + ShariahGuard (Shari’ah-first)
      4) Return structured result and log
    """

    _CONTEXTS: Dict[str, Dict[str, str]] = {
        "stress": {
            "verse": "Ar-Ra’d 13:28 — 'Verily, in the remembrance of Allah do hearts find rest.'",
            "action": "Pray 2 rak‘ah nafl; make dhikr (SubhanAllah, Alhamdulillah, Allahu Akbar) for 5 minutes."
        },
        "anger": {
            "verse": "Al-Imran 3:134 — 'Those who restrain anger and pardon people.'",
            "action": "Say: A‘ūdhu billāhi mina sh-shayṭānir-rajīm, drink water, sit or lie down."
        },
        "sadness": {
            "verse": "At-Tawbah 9:51 — 'Nothing will happen to us except what Allah has decreed.'",
            "action": "Repeat: Ḥasbunallāhu wa ni‘mal-wakīl; gentle breathing with dhikr."
        },
        "laziness": {
            "verse": "Al-Mulk 67:15 — 'Walk in its paths and eat of His provision.'",
            "action": "Make du‘ā: 'Allāhumma innī a‘ūdhu bika minal-‘ajzi wal-kasal' and take a 10-minute starter task."
        },
        "anxiety": {
            "verse": "Ash-Sharḥ 94:5-6 — 'Indeed, with hardship comes ease.'",
            "action": "4-7-8 breathing while reciting short adhkār; schedule brief Qur’an recitation."
        },
        "guilt": {
            "verse": "Az-Zumar 39:53 — 'Do not despair of the mercy of Allah.'",
            "action": "Immediate tawbah: remorse, cease, resolve; pray 2 rak‘ah and make du‘ā for firmness."
        },
        "gratitude": {
            "verse": "Ibrahim 14:7 — 'If you are grateful, I will surely increase you.'",
            "action": "List 3 blessings; say Alhamdulillah 33x; give small ṣadaqah if able."
        },
    }

    _SYNONYMS: Dict[str, List[str]] = {
        "stress":   ["stress", "stressed", "overwhelmed", "pressure", "burnout"],
        "anger":    ["angry", "furious", "mad", "rage", "irritated"],
        "sadness":  ["sad", "down", "hopeless", "crying", "lonely"],
        "laziness": ["lazy", "unmotivated", "tired", "procrastinate", "no energy"],
        "anxiety":  ["anxious", "worry", "panic", "nervous"],
        "guilt":    ["guilty", "regret", "ashamed", "fault"],
        "gratitude":["grateful", "thankful", "blessed"],
    }

    def __init__(
        self,
        *,
        quran_filter: Optional[QuranFilter] = None,
        shariah_guard: Optional[ShariahGuard] = None,
        action_logger: Optional["ActionLogger"] = None,
        mission_log_sink: Optional[callable] = None,  # lambda d: mission_log.append(...)
    ) -> None:
        self.quran_filter = quran_filter or QuranFilter()
        self.shariah_guard = shariah_guard or ShariahGuard()
        self.log = action_logger
        self.mission_log_sink = mission_log_sink

    # -------- public API --------

    def recommend(
        self,
        current_context: str,
        *,
        actor_id: Optional[str] = None,
        source: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not current_context or not str(current_context).strip():
            res = DeenRecommendation(status="error", context=current_context or "", notes=["No context provided"])
            self._sinks(res, actor_id, source)
            return res.to_dict()

        key = self._match_context(str(current_context))
        rec = self._CONTEXTS.get(key, {
            "verse": "Al-Isrā’ 17:82 — 'We send down of the Qur’an that which is healing and mercy for the believers.'",
            "action": "Recite a page of Qur’an, then 5 minutes of silent dhikr."
        })

        # Validations
        quran_check = self.quran_filter.check_text(rec["verse"])
        shariah_check = self.shariah_guard.validate_action(rec["action"])

        # Shari’ah-first gating
        if isinstance(shariah_check, dict) and not shariah_check.get("allowed", True):
            res = DeenRecommendation(
                status="blocked",
                context=current_context,
                recommendation={"verse": rec["verse"], "action": "Advice blocked by Shari’ah rules."},
                quran_validation=quran_check if isinstance(quran_check, dict) else {"result": quran_check},
                shariah_validation=shariah_check,
                notes=["Shari’ah guard denial"],
            )
            self._sinks(res, actor_id, source)
            return res.to_dict()

        # If Qur’an filter warns, add a caution note (don’t block outright)
        notes: List[str] = []
        if isinstance(quran_check, dict) and not quran_check.get("allowed", True):
            notes.append("Qur’an filter raised caution")

        res = DeenRecommendation(
            status="success",
            context=current_context,
            recommendation=rec,
            quran_validation=quran_check if isinstance(quran_check, dict) else {"result": quran_check},
            shariah_validation=shariah_check if isinstance(shariah_check, dict) else {"result": shariah_check},
            notes=notes,
        )
        self._sinks(res, actor_id, source)
        return res.to_dict()

    # -------- helpers --------

    def _match_context(self, text: str) -> str:
        t = text.lower()
        for label, keys in self._SYNONYMS.items():
            if any(k in t for k in keys):
                return label
        # fallback if nothing matched
        for label in self._CONTEXTS.keys():
            if label in t:
                return label
        return "stress"

    # -------- sinks --------

    def _sinks(self, res: DeenRecommendation, actor_id: Optional[str], source: Optional[str]) -> None:
        # ActionLogger
        if self.log:
            try:
                decision = "APPROVED" if res.status == "success" else ("DENIED" if res.status == "blocked" else "INFO")
                self.log.log(
                    action_type="DeenContext",
                    decision=decision,
                    module="deen_context_recommender",
                    status="Success" if res.status != "error" else "Failure",
                    user_input=res.context,
                    actor_id=actor_id,
                    source=source or "context",
                    reason=res.recommendation.get("action", "")[:300],
                    context={"status": res.status},
                    meta={"notes": res.notes},
                )
            except Exception:
                pass

        # MissionLog (optional)
        if self.mission_log_sink:
            try:
                verdict = "halal" if res.status == "success" else ("haram" if res.status == "blocked" else "shubha")
                score = 0.07 if res.status == "success" else (0.8 if res.status == "blocked" else 0.35)
                self.mission_log_sink({
                    "actor_id": actor_id or "user",
                    "activity": "deen_context_recommendation",
                    "verdict": verdict,
                    "score": score,
                    "reasons": [res.recommendation.get("action","")[:120]],
                    "tags": ["context", verdict],
                    "payload": res.to_dict(),
                })
            except Exception:
                pass


# -------- Example quick test --------
if __name__ == "__main__":
    logger = ActionLogger(also_print=True) if ActionLogger else None
    r = DeenContextRecommender(action_logger=logger)
    print(r.recommend("I feel very anxious about exams", actor_id="husnain_ali", source="cli"))
