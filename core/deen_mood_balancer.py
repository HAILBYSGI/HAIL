from core.quran_filter import QuranFilter
from core.intent_classifier import IntentClassifier

class DeenMoodBalancer:
    def __init__(self):
        self.quran_filter = QuranFilter()
        self.intent_classifier = IntentClassifier()
        self.mood_triggers = {
            "anxious": {
                "surah": "Surah Ash-Sharh 94:5-6",
                "advice": "Recite: 'Verily, with hardship comes ease' and breathe deeply 7 times with 'Ya Salam'."
            },
            "depressed": {
                "surah": "Surah Yusuf 12:87",
                "advice": "Make du’a: 'Never give up hope of Allah’s mercy' and offer 2 rakah Salat al-Hajah."
            },
            "unmotivated": {
                "surah": "Surah Al-Inshirah 94:7",
                "advice": "‘So when you are free, strive hard.’ Build new habit: wake up with Fajr and journal purpose."
            },
            "fearful": {
                "surah": "Surah Al-Baqarah 2:286",
                "advice": "Recite the last verse before sleep. Affirm: 'Allah does not burden a soul beyond its capacity.'"
            }
        }

    def balance(self, emotional_input: str):
        """
        Detect emotional mood and recommend a Qur’an-based spiritual adjustment.
        """
        mood = self.intent_classifier.classify_emotion(emotional_input)

        if mood in self.mood_triggers:
            remedy = self.mood_triggers[mood]
        else:
            remedy = {
                "surah": "Surah Al-Ra’d 13:28",
                "advice": "Do dhikr silently: 'Allahu Akbar, SubhanAllah, Alhamdulillah' – 33x each."
            }

        # Validate that the ayah and advice are not in contradiction with Qur’an or ethics
        is_quranic = self.quran_filter.check_text(remedy["surah"])

        return {
            "status": "success",
            "detected_mood": mood,
            "surah_reference": remedy["surah"],
            "spiritual_advice": remedy["advice"],
            "quran_approved": is_quranic
        }
