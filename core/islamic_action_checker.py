# islamic_action_checker.py
# Part of HAIL Phase 3 – AI Ethics, Command & Security Logic

class IslamicActionChecker:
    def __init__(self):
        # This list should be expanded with real-world references or rules from Qur'an/Sunnah
        self.prohibited_keywords = [
            "gambling", "interest", "nudity", "lie", "haram_music", "surveillance_without_consent",
            "astrology", "black_magic", "pornography", "false_testimony"
        ]
        self.doubtful_keywords = [
            "music", "celebrity", "speculation", "luxury_excess", "non_mahram_interaction"
        ]

    def evaluate_action(self, action_text):
        text = action_text.lower()

        for word in self.prohibited_keywords:
            if word in text:
                return {
                    "status": "DENIED",
                    "reason": f"Action contains prohibited content: '{word}'. Not permissible in Islam."
                }

        for word in self.doubtful_keywords:
            if word in text:
                return {
                    "status": "WARNING",
                    "reason": f"Action contains doubtful content: '{word}'. Caution advised."
                }

        return {
            "status": "APPROVED",
            "reason": "Action appears compliant with Islamic values."
        }

# Example usage
if __name__ == "__main__":
    checker = IslamicActionChecker()

    print(checker.evaluate_action("Send birthday music to a non-mahram"))
    print(checker.evaluate_action("Schedule Fajr prayer reminder"))
