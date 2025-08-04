# system_sanctity.py
# Part of HAIL Phase 3 – AI Ethics, Command & Security Logic

import hashlib
import datetime

class SystemSanctity:
    def __init__(self):
        self.verified_founder_id = "husnain.ali.dna.hash"  # Replace with real secure hash
        self.last_breach_attempt = None
        self.fallback_active = False

    def verify_founder(self, input_hash):
        """
        Compares input hash (from fingerprint, voice, DNA) with stored hash.
        """
        if input_hash == self.verified_founder_id:
            return True
        else:
            self.last_breach_attempt = datetime.datetime.now()
            self.fallback_active = True
            return False

    def can_modify_system(self, input_hash):
        """
        Returns True if modification is allowed. Triggers lockdown otherwise.
        """
        if self.verify_founder(input_hash):
            self.fallback_active = False
            return True
        else:
            return False

    def status(self):
        return {
            "fallback_mode": self.fallback_active,
            "last_breach": self.last_breach_attempt.strftime("%Y-%m-%d %H:%M:%S") if self.last_breach_attempt else "None"
        }

# Example usage
if __name__ == "__main__":
    sanctity = SystemSanctity()
    attempt = sanctity.can_modify_system("unauthorized.hash")
    print("Modify Allowed:", attempt)
    print("System Status:", sanctity.status())
