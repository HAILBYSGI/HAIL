# core/violation_handler.py

from core.quranic_violation_detector import QuranicViolationDetector

class ViolationHandler:
    def __init__(self):
        self.detector = QuranicViolationDetector()
        self.action_log = []

    def handle_input(self, user_input, source="unknown"):
        result = self.detector.detect_violation(user_input)
        if result["violation"]:
            action_taken = self.take_action(result["matched_terms"], source)
            return {
                "status": "blocked",
                "message": "Action denied due to Shari’ah violation.",
                "details": result,
                "action_taken": action_taken
            }
        return {
            "status": "allowed",
            "message": "Input accepted. No violations found."
        }

    def take_action(self, violations, source):
        log_entry = {
            "source": source,
            "violations": violations,
            "response": "Blocked & Logged",
        }
        self.action_log.append(log_entry)
        self.alert_founder(source, violations)
        return log_entry

    def alert_founder(self, source, violations):
        print(f"[ALERT] Violation detected from {source}: {violations}")
        # Placeholder: Can be expanded to send email/SMS/notification

    def get_action_log(self):
        return self.action_log
