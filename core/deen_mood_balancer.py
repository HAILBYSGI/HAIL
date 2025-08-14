# core/deen_mood_balancer.py
# HAIL — DeenMoodBalancer (Upgraded)
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional

from core.quran_filter import QuranFilter
from core.intent_classifier import IntentClassifier

try:
    from core.action_logger import ActionLogger
except Exception:  # pragma: no cover
    ActionLogger = None  # type: ignore


@dataclass
class MoodBalanceResult:
    status: str                       # "success" | "error"
    detected_mood: str
    surah_reference: str
    spiritual_advice: str
    quran_approved: Dict[str, Any] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DeenMoodBalancer:
    """
    Detect emotional mood and recommend a Qur’an-based adjustment.
    Pipeline:
      1) Classify mood (keywords → IntentClassifier)
      2) Map to Qur’anic verse + spiritual practice
      3) Validate with QuranFilter (authenticity/caution)
      4) Return structured result and log to sinks
    """

    _MOOD_MAP: Dict[str, Dict[str, str]] = {
        "anxious": {
            "surah": "Surah Ash-Sharḥ 94:5-6",
            "advice": "Recite: 'Inna ma‘al-‘usri yusrā' and do 7 deep breaths with 'Yā Salām'."
        },
        "depressed": {
            "surah": "Surah Yūsuf 12:87",
            "advice": "Make du‘ā of hope; pray 2 rak‘ah Ṣalāt al-Ḥājah; reflect on Allah’s mercy."
        },
        "unmotivated": {
            "surah": "Surah Al-Inshirāḥ 94:7",
            "advice": "‘When you are free, strive’ — do wuḍū, plan one small task, start with Bismillah."
        },
        "fearful": {
            "surah": "Surah Al-Baqarah 2:286",
            "advice": "Recite the last āyah before sleep; affirm: 'Allah does not burden beyond capacity.'"
        },
        "sad": {
            "surah": "Surah At-Tawbah 9:51",
            "advice": "Repeat: Ḥasbunallāhu wa ni‘mal-wakīl, then a page of Qur’an with tadabbur."
        },
        "angry": {
            "surah": "Surah Āl ‘Imrān 3:134",
            "advice": "Seek refuge (A‘ūdhu billāh), drink water, sit/lie down, forgive where possible."
        },
        "envy": {
            "surah": "Surah Al-Falaq 113:5",
            "advice": "Recite Al-Falaq and make du‘ā for the one you envy; practice gratitude list."
        },
    }

    _SYNONYMS: Dict[str, List[str]] = {
        "anxious": ["anxious", "anxiety", "panic", "nervous", "worry"],
        "depressed": ["depressed", "down", "hopeless", "empty"],
        "unmotivated": ["unmotivated", "lazy", "no energy", "procrastinate"],
        "fearful": ["fear", "afraid", "scared"],
        "sad": ["sad", "crying", "lonely"],
        "angry": ["angry", "furious", "rage", "irritated"],
        "envy": ["jealous", "envy", "envious", "hasad"],
    }

    def __init__(
        self,
        *,
        quran_filter: Optional[QuranFilter] = None,
        intent_classifier: Optional[IntentClassifier] = None,
        action_logger: Optional["ActionLogger"] = None,
        mission_log_sink: Optional[callable] = None,  # lambda d: mission_log.append(...)
    ) -> None:
        self.quran_filter = quran_filter or QuranFilter()
        self.intent_classifier = intent_classifier or IntentClassifier()
        self.log = action_logger
        self.mission_log_sink = mission_log_sink

    # --------------- Public API ---------------

    def balance(self, emotional_input: str, *, actor_id: Optional[str] = None, source: Optional[str] = None) -> Dict[str, Any]:
        if not emotional_input or not str(emotional_input).strip():
            res = MoodBalanceResult(status="error", detected_mood="", surah_reference="", spiritual_advice="", notes=["No input provided"])
            self._sinks(res, actor_id, source)
            return res.to_dict()

        # 1) classify via IntentClassifier first (your model)
        mood = self.intent_classifier.classify_emotion(emotional_input)
        # 2) fallback synonyms if classifier returns generic text
        mood = self._match_mood(emotional_input, default=mood)

        # 3) choose remedy (fallback safe default)
        remedy = self._MOOD_MAP.get(mood, {
            "surah": "Surah Ar-Ra‘d 13:28",
            "advice": "Do dhikr quietly: Allahu Akbar, SubḥānAllāh, Alḥamdulillāh (33× each); a page of Qur’an."
        })

        # 4) validate with QuranFilter (don’t block; add caution notes if needed)
        quran_check = self.quran_filter.check_text(remedy["surah"])
        notes: List[str] = []
        if isinstance(quran_check, dict) and not quran_check.get("allowed", True):
            notes.append("Qur’an filter raised caution")

        res = MoodBalanceResult(
            status="success",
            detected_mood=mood,
            surah_reference=remedy["surah"],
            spiritual_advice=remedy["advice"],
            quran_approved=quran_check if isinstance(quran_check, dict) else {"result": quran_check},
            notes=notes,
        )
        self._sinks(res, actor_id, source)
        return res.to_dict()

    # --------------- Helpers ---------------

    def _match_mood(self, text: str, *, default: Optional[str]) -> str:
        t = text.lower()
        for label, keys in self._SYNONYMS.items():
            if any(k in t for k in keys):
                return label
        # if classifier returned something already covered, keep it
        if default and default in self._MOOD_MAP:
            return default
        return "anxious"  # gentle default

    # --------------- Sinks ---------------

    def _sinks(self, res: MoodBalanceResult, actor_id: Optional[str], source: Optional[str]) -> None:
        # Action logger
        if self.log:
            try:
                self.log.log(
                    action_type="MoodBalance",
                    decision="APPROVED" if res.status == "success" else "ERROR",
                    module="deen_mood_balancer",
                    status="Success" if res.status == "success" else "Failure",
                    user_input=res.detected_mood,
                    actor_id=actor_id,
                    source=source or "mood",
                    reason=res.spiritual_advice[:300],
                    context={"surah": res.surah_reference},
                    meta={"notes": res.notes},
                )
            except Exception:
                pass

        # Mission log (optional)
        if self.mission_log_sink:
            try:
                self.mission_log_sink({
                    "actor_id": actor_id or "user",
                    "activity": "mood_balance",
                    "verdict": "halal",
                    "score": 0.06,
                    "reasons": [res.spiritual_advice[:120]],
                    "tags": ["mood", res.detected_mood or "unknown"],
                    "payload": res.to_dict(),
                })
            except Exception:
                pass


# ---------------- Example quick test ----------------
if __name__ == "__main__":
    logger = ActionLogger(also_print=True) if ActionLogger else None  # type: ignore
    mb = DeenMoodBalancer(action_logger=logger)
    print(mb.balance("I feel very anxious about work and keep procrastinating", actor_id="husnain_ali"))
