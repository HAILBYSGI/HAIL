# core/quranic_violation_detector.py

import re

class QuranicViolationDetector:
    def __init__(self, prohibited_keywords=None):
        self.prohibited_keywords = prohibited_keywords or [
            "interest", "riba", "gambling", "alcohol", "nudity", "haram", "shirk", "slander",
            "backbiting", "black magic", "fortune telling", "zina", "porn", "lie", "deceit",
            "oppression", "murder", "insult", "suicide", "blasphemy"
        ]
        self.violation_log = []

    def scan_input(self, user_input):
        matches = []
        lower_input = user_input.lower()
        for word in self.prohibited_keywords:
            if re.search(r'\b' + re.escape(word) + r'\b', lower_input):
                matches.append(word)
        return matches

    def detect_violation(self, user_input):
        violations = self.scan_input(user_input)
        if violations:
            self.violation_log.append({
                "input": user_input,
                "violations": violations
            })
            return {
                "violation": True,
                "reason": "Qur’an-based ethical filter triggered",
                "matched_terms": violations
            }
        return {
            "violation": False,
            "reason": "No Qur’anic violation detected"
        }

    def get_violation_log(self):
        return self.violation_log
