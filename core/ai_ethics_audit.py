# core/ai_ethics_audit.py

from datetime import datetime

class AIEthicsAudit:
    def __init__(self):
        self.audit_log = []
        self.violation_count = 0
        self.verified_rules = [
            "no_shirk", "no_backbiting", "no_falsehood",
            "respect_quran", "preserve_modesty", "founder_alignment"
        ]

    def log_action(self, action_type, details, is_compliant=True):
        timestamp = datetime.utcnow().isoformat()
        entry = {
            "timestamp": timestamp,
            "action_type": action_type,
            "details": details,
            "compliant": is_compliant
        }
        self.audit_log.append(entry)

        if not is_compliant:
            self.violation_count += 1
            print(f"[ETHICS WARNING] {action_type} violated ethics at {timestamp}: {details}")

    def check_against_ethics(self, action_dict):
        """
        action_dict should include:
        {
            "type": "response/generation/execution",
            "content": "text or description of action",
            "tags": ["modesty", "truth", "shirk_check", ...]
        }
        """
        for tag in action_dict.get("tags", []):
            if tag not in self.verified_rules:
                self.log_action(action_dict["type"], f"Unverified tag: {tag}", is_compliant=False)
                return False

        # You can expand this logic to handle more detailed matching.
        self.log_action(action_dict["type"], action_dict["content"], is_compliant=True)
        return True

    def get_audit_summary(self):
        return {
            "total_checks": len(self.audit_log),
            "violations": self.violation_count,
            "last_check": self.audit_log[-1] if self.audit_log else "No actions logged"
        }

    def reset_audit(self):
        self.audit_log = []
        self.violation_count = 0
