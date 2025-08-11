from datetime import datetime
from core.founder_alert import FounderAlert
from core.shariah_guard import ShariahGuard

class DeenEmergencyMode:
    def __init__(self):
        self.status = "OFF"
        self.alert = FounderAlert()
        self.guard = ShariahGuard()

    def activate(self, reason=""):
        """
        Activates emergency mode. Overrides normal systems and tightens restrictions.
        """
        self.status = "ON"
        self.timestamp = datetime.now()
        self.reason = reason
        self.guard.enforce_max_filter_level()
        self.alert.send("⚠️ DEEN EMERGENCY MODE ACTIVATED", f"Reason: {reason}")
        return {
            "mode": self.status,
            "reason": reason,
            "timestamp": self.timestamp.isoformat(),
            "impact": [
                "All entertainment systems blocked",
                "Non-essential commands disabled",
                "Focus redirected to Qur’an, Salah, Dhikr",
                "Founder notified",
            ]
        }

    def deactivate(self):
        """
        Deactivates emergency mode and restores normal operations.
        """
        self.status = "OFF"
        self.timestamp = datetime.now()
        self.guard.reset_filter_level()
        self.alert.send("✅ DEEN EMERGENCY MODE DEACTIVATED", "System has returned to normal operation.")
        return {
            "mode": self.status,
            "timestamp": self.timestamp.isoformat(),
            "restored_to": "standard ethical filters and user workflow"
        }

    def get_status(self):
        return {
            "deen_emergency_status": self.status,
            "last_updated": getattr(self, "timestamp", "Not set"),
            "reason": getattr(self, "reason", "Not set")
        }
