from core.islamic_action_checker import IslamicActionChecker
from core.founder_alert import FounderAlert
from core.quranic_violation_detector import QuranicViolationDetector
from core.taqwa_alert_manager import TaqwaAlertManager

class DeenGuardianTrigger:
    def __init__(self):
        self.action_checker = IslamicActionChecker()
        self.quran_violation = QuranicViolationDetector()
        self.taqwa_manager = TaqwaAlertManager()
        self.alert = FounderAlert()

    def evaluate_user_action(self, action):
        """
        Triggers deen guardian check for the given user action. Flags inappropriate behavior,
        activates taqwa alert, and optionally blocks action or suggests correction.
        """
        response = {}

        if not self.action_checker.is_halal(action):
            violation_msg = f"⛔ Action flagged as possibly haram: {action}"
            self.quran_violation.flag_violation(action)
            self.taqwa_manager.trigger_taqwa_alert(action)
            self.alert.send("🚨 DEEN GUARDIAN ALERT", violation_msg)
            response["status"] = "blocked"
            response["message"] = violation_msg

        else:
            response["status"] = "allowed"
            response["message"] = f"✅ Action approved: {action}"

        return response
