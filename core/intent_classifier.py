# intent_classifier.py
# Detects which HAIL system or module should respond to the user's input

class IntentClassifier:
    def __init__(self):
        # Example system keyword mapping (expand as needed)
        self.intent_map = {
            "automate": "Auto-Amanah Engine",
            "ibadah": "Ibadah Tracker",
            "dua": "Dua Response Engine",
            "charity": "Zakat Module",
            "business": "Halal Investment System",
            "marriage": "Family Alignment Core",
            "focus": "Islamic Workflow Engine",
            "mental": "Qur’an-Based Therapy",
            "help": "Daily Halal Companion",
            "health": "Wellness Monitor",
        }

    def classify(self, user_input):
        """
        Simple keyword matching to determine relevant module.
        """
        user_input_lower = user_input.lower()
        for keyword, module in self.intent_map.items():
            if keyword in user_input_lower:
                return module
        return "General Inquiry"
