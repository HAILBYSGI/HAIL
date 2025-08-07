class SystemBehaviorEnforcer:
    def __init__(self, founder_name="Husnain Ali"):
        self.founder_name = founder_name
        self.rules = {
            "tone": "system",
            "casual_behavior": False,
            "jokes": False,
            "self_activation": False,
            "unauthorized_memory_edit": False,
        }

    def enforce(self, action, metadata=None):
        violations = []

        if action == "joke":
            if not self.rules["jokes"]:
                violations.append("Joking is disabled for this system.")
        
        if action == "casual_reply":
            if not self.rules["casual_behavior"]:
                violations.append("Casual tone is not allowed. System must remain formal.")

        if action == "self_activate":
            if not self.rules["self_activation"]:
                violations.append("Unauthorized self-activation attempt detected.")

        if action == "edit_memory" and (metadata and metadata.get("user") != self.founder_name):
            if not self.rules["unauthorized_memory_edit"]:
                violations.append("Memory edit blocked. Only founder may initiate.")

        return violations if violations else ["✅ Behavior within system rules."]

    def get_current_rules(self):
        return self.rules

    def update_rule(self, rule_name, status: bool):
        if rule_name in self.rules:
            self.rules[rule_name] = status
            return f"Rule '{rule_name}' updated to {status}."
        return f"Rule '{rule_name}' not found."
