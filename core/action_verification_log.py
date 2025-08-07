# core/action_verification_log.py

from datetime import datetime

class ActionVerificationLog:
    def __init__(self):
        self.verified_actions = []
        self.unverified_attempts = []

    def log_action(self, action_name, initiator, verified, verification_source, metadata=None):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "action": action_name,
            "initiator": initiator,
            "verified": verified,
            "verification_source": verification_source,
            "metadata": metadata or {}
        }

        if verified:
            self.verified_actions.append(log_entry)
            print(f"[ACTION VERIFIED] {action_name} by {initiator}")
        else:
            self.unverified_attempts.append(log_entry)
            print(f"[⚠️ UNVERIFIED ACTION] {action_name} attempted by {initiator}")

    def get_verified_actions(self):
        return self.verified_actions

    def get_unverified_attempts(self):
        return self.unverified_attempts

    def get_last_action_status(self):
        if self.verified_actions:
            return self.verified_actions[-1]
        elif self.unverified_attempts:
            return self.unverified_attempts[-1]
        else:
            return "No actions logged yet."

    def reset_logs(self):
        self.verified_actions = []
        self.unverified_attempts = []
