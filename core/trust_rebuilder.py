class TrustRebuilder:
    def __init__(self):
        self.trust_score = 100
        self.repair_logs = []

    def degrade_trust(self, reason, points=10):
        self.trust_score = max(0, self.trust_score - points)
        self.repair_logs.append({
            "action": "degrade",
            "reason": reason,
            "change": -points,
            "new_score": self.trust_score
        })
        return f"⚠️ Trust score decreased to {self.trust_score} due to: {reason}"

    def rebuild_trust(self, action, points=5):
        self.trust_score = min(100, self.trust_score + points)
        self.repair_logs.append({
            "action": "rebuild",
            "reason": action,
            "change": points,
            "new_score": self.trust_score
        })
        return f"✅ Trust score increased to {self.trust_score} after: {action}"

    def get_trust_score(self):
        return self.trust_score

    def get_repair_logs(self):
        return self.repair_logs

    def reset_trust(self):
        self.trust_score = 100
        self.repair_logs.clear()
        return "🔄 Trust score reset to 100 and logs cleared."
