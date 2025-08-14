# Phase 3.xx – deen_focus_restorer.py
# -----------------------------------------------------------------------------
# Purpose:
# - Identify mental states causing loss of focus
# - Provide Qur’anic reminders and Islamic strategies to restore concentration
# - Validate with QuranFilter for authenticity
# - Log all interventions for accountability
# -----------------------------------------------------------------------------

from core.quran_filter import QuranFilter
from core.intent_classifier import IntentClassifier
from core.deen_compliance_logger import DeenComplianceLogger
from core.mission_logger import MissionLogger

class DeenFocusRestorer:
    def __init__(self):
        self.quran_filter = QuranFilter()
        self.intent_classifier = IntentClassifier()
        self.logger = DeenComplianceLogger()
        self.mission_log = MissionLogger()

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
        Steps:
        1. Classify mental state
        2. Retrieve Qur’an + advice strategy
        3. Validate Qur’anic reference
        4. Log action & return result
        """
        # Step 1 – Classify
        condition = self.intent_classifier.classify_emotion(mental_state)

        # Step 2 – Retrieve matching strategy
        strategy = self.focus_triggers.get(condition, {
            "surah": "Surah Al-Kahf 18:28",
            "advice": "Sit quietly, recite the verse, and set a 10-minute timer for focused work with niyyah."
        })

        # Step 3 – Validate Qur’an authenticity
        quran_check = self.quran_filter.check_text(strategy["surah"])

        # Step 4 – Compile result
        result = {
            "status": "success",
            "identified_distraction": condition,
            "quran_reference": strategy["surah"],
            "focus_advice": strategy["advice"],
            "verified_by_quran_filter": quran_check
        }

        # Step 5 – Log compliance & mission
        self.logger.log_entry(
            module="DeenFocusRestorer",
            action=f"Restoring focus for condition: {condition}",
            result=result,
            compliant=quran_check.get("status") == "approved",
            notes="Focus restoration executed"
        )

        self.mission_log.record(
            source="DeenFocusRestorer",
            event_type="focus_restoration",
            details=result
        )

        return result

# ---------------- Example Usage ----------------
if __name__ == "__main__":
    restorer = DeenFocusRestorer()
    sample = restorer.restore_focus("Feeling distracted and lazy")
    print(sample)
