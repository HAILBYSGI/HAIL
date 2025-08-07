class TaqwaSensitivityController:
    def __init__(self, base_level=50):
        self.taqwa_level = base_level  # 0 = insensitive, 100 = hyper-aware
        self.history = []

    def adjust_taqwa(self, context, increase=True, value=5):
        change = value if increase else -value
        self.taqwa_level = max(0, min(100, self.taqwa_level + change))

        self.history.append({
            "context": context,
            "change": "+" + str(value) if increase else "-" + str(value),
            "new_level": self.taqwa_level
        })

        return {
            "status": "updated",
            "taqwa_level": self.taqwa_level,
            "context": context
        }

    def get_current_level(self):
        return self.taqwa_level

    def is_alert(self):
        if self.taqwa_level >= 80:
            return True  # Highly sensitive
        elif self.taqwa_level <= 20:
            return False  # Danger zone: spiritually dull
        else:
            return None  # Normal sensitivity

    def get_history(self):
        return self.history

    def reset_taqwa(self):
        self.taqwa_level = 50
        self.history = []
        return "🔄 Taqwa sensitivity reset to neutral level (50)."
