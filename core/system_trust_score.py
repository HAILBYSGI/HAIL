# core/system_trust_score.py

import datetime

class SystemTrustScore:
    def __init__(self):
        self.trust_scores = {}
        self.history = []

    def initialize_module(self, module_name, base_score=100):
        if module_name not in self.trust_scores:
            self.trust_scores[module_name] = base_score

    def adjust_score(self, module_name, change, reason=""):
        if module_name not in self.trust_scores:
            self.initialize_module(module_name)

        old_score = self.trust_scores[module_name]
        new_score = max(0, min(100, old_score + change))
        self.trust_scores[module_name] = new_score

        log_entry = {
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "module": module_name,
            "old_score": old_score,
            "new_score": new_score,
            "change": change,
            "reason": reason
        }
        self.history.append(log_entry)
        return log_entry

    def get_score(self, module_name):
        return self.trust_scores.get(module_name, 0)

    def get_all_scores(self):
        return dict(self.trust_scores)

    def flag_low_trust_modules(self, threshold=50):
        return [module for module, score in self.trust_scores.items() if score < threshold]

    def reset_score(self, module_name, score=100):
        self.trust_scores[module_name] = score
