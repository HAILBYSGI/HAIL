# command_handler.py
# Part of HAIL Phase 3 – AI Ethics, Command & Security Logic

from core.intent_classifier import IntentClassifier
from core.shariah_guard import ShariahGuard
from core.halal_task_router import HalalTaskRouter

class CommandHandler:
    def __init__(self):
        self.intent_classifier = IntentClassifier()
        self.shariah_guard = ShariahGuard()
        self.task_router = HalalTaskRouter()

    def handle_command(self, user_command):
        intent = self.intent_classifier.classify(user_command)

        if not self.shariah_guard.is_halal(user_command):
            return {
                "status": "rejected",
                "reason": "Command not compliant with Islamic principles.",
                "intent": intent
            }

        task_result = self.task_router.route_task(user_command)

        if task_result["status"] == "accepted":
            return {
                "status": "ready",
                "action": task_result["routed_to"],
                "intent": intent,
                "confidence": task_result["confidence"]
            }
        else:
            return {
                "status": "rejected",
                "reason": "Unable to route command",
                "intent": intent
            }

# Example usage
if __name__ == "__main__":
    ch = CommandHandler()
    print(ch.handle_command("Send reminder for Fajr salah"))
