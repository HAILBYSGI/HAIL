from core.shariah_guard import ShariahGuard
from core.intent_classifier import IntentClassifier

class DeenEmotionGuard:
    def __init__(self):
        self.shariah_guard = ShariahGuard()
        self.intent_classifier = IntentClassifier()
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
        Monitors user’s emotional state and recommends Islamic interventions for spiritual correction.
        """
        emotion = self.intent_classifier.classify_emotion(detected_emotion)

        if emotion in self.forbidden_emotions:
            details = self.forbidden_emotions[emotion]
        else:
            details = {
                "hadith": "Every soul will be tested with hardship, but Allah loves those who are patient.",
                "quran": "Surah Al-Baqarah 2:153",
                "remedy": "Perform salah, recite ‘Inna Lillahi wa inna ilayhi raji’un’ and make du’a for strength."
            }

        shariah_check = self.shariah_guard.verify_emotion(emotion)

        return {
            "status": "monitored",
            "detected_emotion": emotion,
            "quran_reference": details["quran"],
            "hadith_reference": details["hadith"],
            "prescribed_remedy": details["remedy"],
            "approved_by_shariah_guard": shariah_check
        }
