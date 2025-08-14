# system_behavior_enforcer.py
# Part of HAIL Phase 3 – AI Ethics, Command & Security Logic
# Ensures system interactions remain formal, secure, and founder-governed.

class SystemBehaviorEnforcer:
    """
    Enforces predefined behavior rules for the HAIL system,
    ensuring no deviation from founder-defined tone, actions, or permissions.
    """

    def __init__(self, founder_name: str = "Husnain Ali"):
        self.founder_name = founder_name
        self.rules = {
            "tone": "system",  # could be 'system' or 'casual'
            "casual_behavior": False,
            "jokes": False,
            "self_activation": False,
            "unauthorized_memory_edit": False,
        }

    def enforce(self, action: str, metadata: dict | None = None) -> list[str]:
        """
        Check if the given action violates any system rules.
        Returns a list of violations, or ✅ if no violations are found.
        """
        violations = []

        if action == "joke" and not self.rules["jokes"]:
            violations.append("Joking is disabled for this system.")
        
        if action == "casual_reply" and not self.rules["casual_behavior"]:
            violations.append("Casual tone is not allowed. System must remain formal.")

        if action == "self_activate" and not self.rules["self_activation"]:
            violations.append("Unauthorized self-activation attempt detected.")

        if action == "edit_memory":
            if metadata and metadata.get("user") != self.founder_name:
                if not self.rules["unauthorized_memory_edit"]:
                    violations.append("Memory edit blocked. Only founder may initiate.")

        return violations if violations else ["✅ Behavior within system rules."]

    def get_current_rules(self) -> dict:
        """Returns the current behavior enforcement rules."""
        return self.rules

    def update_rule(self, rule_name: str, status: bool) -> str:
        """
        Update a specific system rule.
        Returns a confirmation string or an error message.
        """
        if rule_name in self.rules:
            self.rules[rule_name] = status
            return f"Rule '{rule_name}' updated to {status}."
        return f"Rule '{rule_name}' not found."


# Example usage
if __name__ == "__main__":
    enforcer = SystemBehaviorEnforcer()
    print(enforcer.enforce("joke"))
    print(enforcer.update_rule("jokes", True))
    print(enforcer.enforce("joke"))
