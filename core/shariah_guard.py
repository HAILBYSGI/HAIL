# shariah_guard.py
# Filters HAIL actions based on Qur'an and Sunnah compliance

class ShariahGuard:
    def __init__(self):
        # Add or expand with more rulings later
        self.prohibited_keywords = [
            "interest", "riba", "gambling", "nudity", "forbidden", "alcohol", "music-haram"
        ]
        self.forced_actions_blocked = True  # No compulsion in deen

    def is_halal_action(self, user_input):
        """
        Scans for clearly haram or restricted terms.
        """
        lower_input = user_input.lower()
        for word in self.prohibited_keywords:
            if word in lower_input:
                return False
        return True

    def filter_action(self, user_input):
        """
        Return True if action is allowed; False if blocked by Islamic law.
        """
        if not self.is_halal_action(user_input):
            return False
        # Add more complex fatwa matching later
        return True
