from core.quran_filter import QuranFilter
from core.intent_classifier import IntentClassifier

class DeenFocusRestorer:
    def __init__(self):
        self.quran_filter = QuranFilter()
        self.intent_classifier = IntentClassifier()
        self.focus_triggers = {
            "distracted": {
                "surah": "Surah Al-Asr 103:1–3",
                "advice": "Reflect on time: recite Surah Al-Asr slowly. Make niyyah for one small task with ihsan."
            },
            "lazy": {
                "surah": "Surah Al-Mu’minun 23:1-2",
                "advice": "‘Successful are the believers who are humble in prayer.’ Do wudhu and pray 2 rakah with full presence."
            },
            "overwhelmed": {
                "surah": "Surah Al-Baqarah 2:286",
                "advice": "Break the task into small parts. Say: 'La yukallifullahu nafsan illa wus'aha' and begin Bismillah."
            }
        }

    def restore_focus(self, mental_state: str):
        """
        Detects current cognitive distraction or weakness and suggests Islamic re-centering.
        """
        condition = self.intent_classifier.classify_emotion(mental_state)

        if condition in self.focus_triggers:
            strategy = self.focus_triggers[condition]
        else:
            strategy = {
                "surah": "Surah Al-Kahf 18:28",
                "advice": "Sit quietly, recite the verse, and set a 10-minute timer for focused work with niyyah."
            }

        is_valid = self.quran_filter.check_text(strategy["surah"])

        return {
            "status": "success",
            "identified_distraction": condition,
            "quran_reference": strategy["surah"],
            "focus_advice": strategy["advice"],
            "verified_by_quran_filter": is_valid
        }
