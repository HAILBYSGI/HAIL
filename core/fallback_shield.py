# fallback_shield.py
# Part of HAIL Phase 3 – AI Ethics, Command & Security Logic

import datetime
import os

class FallbackShield:
    def __init__(self, shield_log_path="hail_logs/fallback_log.txt"):
        self.active = False
        self.trigger_reason = None
        self.trigger_time = None
        self.shield_log_path = shield_log_path
        os.makedirs(os.path.dirname(self.shield_log_path), exist_ok=True)

    def activate(self, reason):
        """
        Triggers the fallback system and logs the event.
        """
        self.active = True
        self.trigger_reason = reason
        self.trigger_time = datetime.datetime.now()

        self._log_event("ACTIVATED", reason)

    def deactivate(self, founder_confirmed=False):
        """
        Deactivates shield only if founder confirms.
        """
        if founder_confirmed:
            self._log_event("DEACTIVATED", "Founder override verified.")
            self.active = False
            self.trigger_reason = None
            self.trigger_time = None
            return True
        else:
            return False

    def status(self):
        return {
            "active": self.active,
            "trigger_reason": self.trigger_reason,
            "trigger_time": self.trigger_time.strftime("%Y-%m-%d %H:%M:%S") if self.trigger_time else "None"
        }

    def _log_event(self, status, reason):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = (
            f"---\n"
            f"Status     : {status}\n"
            f"Timestamp  : {timestamp}\n"
            f"Reason     : {reason}\n"
        )
        with open(self.shield_log_path, "a", encoding="utf-8") as file:
            file.write(log_entry + "\n")

# Example usage
if __name__ == "__main__":
    shield = FallbackShield()
    shield.activate("Unauthorized system modification attempt")
    print(shield.status())
