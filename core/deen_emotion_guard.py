# Phase 3.xx – deen_emotion_guard.py
# -----------------------------------------------------------------------------
# Purpose:
# - Detect and respond to forbidden or harmful emotions per Islamic guidance
# - Recommend Qur’anic verses, hadith, and remedies
# - Validate advice with ShariahGuard before delivery
# - Log actions for audit and transparency
# -----------------------------------------------------------------------------

from core.shariah_guard import ShariahGuard
from core.intent_classifier import IntentClassifier
from core.deen_compliance_logger import DeenComplianceLogger
from core.mission_logger import MissionLogger

class DeenEmotionGuard:
    def __init__(self):
        self.shariah_guard = ShariahGuard()
        self.intent_classifier = IntentClassifier()
        self.logger = DeenComplianceLogger()
        self.mission_log = MissionLogger()

        # Centralized forbidden emotions repository
        self.forbidden_emotions = {
            "envy": {
                "hadith": "Avoid envy, for envy devours good deeds just as fire devours wood. – Abu Dawood",
                "quran": "Surah Al-Falaq 113:5",
                "remedy": "Recite Surah Al-Falaq thrice and make du’a for the one you envy."
            },
            "arrogance": {
                "hadith": "No one who has an atom’s weight of arrogance in his heart will enter Paradise. – Muslim",
                "quran": "Surah Luqman 31:18",
                "remedy": "Make sajdah of humility and do dhikr of ‘Subhana Rabbiyal A’la’ 33 times."
            },
            "anger": {
                "hadith": "Do not get angry. – Bukhari",
                "quran": "Surah Al-Imran 3:134",
                "remedy": "Make wudhu, sit down if standing, and seek refuge with Allah from Shaytan."
            }
        }

    def guard_emotion(self, detected_emotion: str):
        """
        Analyzes and addresses the user’s emotional state with Islamic remedies.
        Steps:
        1. Classify detected emotion
        2. Lookup recommended Qur’an & Hadith guidance
        3. Validate with ShariahGuard
        4. Log action for compliance & auditing
        """
        # Step 1: Classify emotion (from speech, text, or other sensors)
        emotion = self.intent_classifier.classify_emotion(detected_emotion)

        # Step 2: Get guidance
        details = self.forbidden_emotions.get(emotion, {
            "hadith": "Every soul will be tested with hardship, but Allah loves those who are patient.",
            "quran": "Surah Al-Baqarah 2:153",
            "remedy": "Perform salah, recite ‘Inna Lillahi wa inna ilayhi raji’un’ and make du’a for strength."
        })

        # Step 3: Validate with ShariahGuard
        shariah_check = self.shariah_guard.verify_emotion(emotion)

        # Step 4: Prepare result
        result = {
            "status": "monitored",
            "detected_emotion": emotion,
            "quran_reference": details["quran"],
            "hadith_reference": details["hadith"],
            "prescribed_remedy": details["remedy"],
            "approved_by_shariah_guard": shariah_check
        }

        # Step 5: Log for compliance & mission history
        self.logger.log_entry(
            module="DeenEmotionGuard",
            action=f"Emotion detected: {emotion}",
            result=result,
            compliant=shariah_check.get("status") == "approved",
            notes="Emotion monitoring executed"
        )

        self.mission_log.record(
            source="DeenEmotionGuard",
            event_type="emotion_analysis",
            details=result
        )

        return result

# ---------------- Example Usage ----------------
if __name__ == "__main__":
    guard = DeenEmotionGuard()
    sample = guard.guard_emotion("I feel very angry right now")
    print(sample)
