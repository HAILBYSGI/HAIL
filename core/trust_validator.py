# trust_validator.py
# Part of HAIL Phase 3 – AI Ethics, Command & Security Logic

class TrustValidator:
    def __init__(self):
        self.verified_tokens = set()
        self.verified_voiceprints = {}
        self.verified_devices = set()
        self.founder_id = "husnain.ali"

    def add_verified_token(self, token):
        self.verified_tokens.add(token)

    def add_verified_voice(self, user_id, voice_hash):
        self.verified_voiceprints[user_id] = voice_hash

    def add_verified_device(self, device_id):
        self.verified_devices.add(device_id)

    def is_trusted(self, user_id, device_id=None, token=None, voice_hash=None):
        trust_score = 0

        if user_id == self.founder_id:
            trust_score += 5

        if token and token in self.verified_tokens:
            trust_score += 2

        if device_id and device_id in self.verified_devices:
            trust_score += 2

        if voice_hash and self.verified_voiceprints.get(user_id) == voice_hash:
            trust_score += 3

        return trust_score >= 5

    def trust_report(self, user_id, device_id=None, token=None, voice_hash=None):
        if self.is_trusted(user_id, device_id, token, voice_hash):
            return {
                "status": "TRUSTED",
                "message": "Source validated and authorized for HAIL execution."
            }
        return {
            "status": "UNTRUSTED",
            "message": "Source failed to meet trust requirements. Execution denied."
        }

# Example
if __name__ == "__main__":
    validator = TrustValidator()
    validator.add_verified_token("12345")
    validator.add_verified_voice("husnain.ali", "voicehash001")
    validator.add_verified_device("raspi-01")

    report = validator.trust_report("husnain.ali", "raspi-01", "12345", "voicehash001")
    print(report)
