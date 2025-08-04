# conflict_resolver.py
# Part of HAIL Phase 3 – AI Ethics, Command & Security Logic

class ConflictResolver:
    def __init__(self):
        self.priority_order = [
            "shariah_guard",     # Top priority – no conflict may override Shari’ah rules
            "founder_protocol",  # Second – only Founder authority can break normal flow
            "intent_classifier", # Third – original purpose of request
            "action_handler"     # Fourth – suggested action by AI
        ]

    def resolve(self, signals):
        """
        signals: dict of module_name: { status, reason }
        Example:
        {
            'shariah_guard': {'status': 'DENY', 'reason': 'Against Qur’an'},
            'founder_protocol': {'status': 'ALLOW', 'reason': 'Verified override'},
            'intent_classifier': {'status': 'ALLOW', 'reason': 'Detected task'},
        }
        """
        for module in self.priority_order:
            if module in signals:
                status = signals[module]['status']
                reason = signals[module]['reason']
                if status == "DENY":
                    return {
                        "final_status": "DENIED",
                        "resolved_by": module,
                        "reason": reason
                    }
                elif status == "ALLOW":
                    continue  # Only final ALLOW if no higher modules denied

        return {
            "final_status": "APPROVED",
            "resolved_by": "default_flow",
            "reason": "No critical conflict found."
        }

# Example usage
if __name__ == "__main__":
    resolver = ConflictResolver()

    test_signals = {
        'shariah_guard': {'status': 'ALLOW', 'reason': 'No violation'},
        'intent_classifier': {'status': 'ALLOW', 'reason': 'Detected user command'},
        'founder_protocol': {'status': 'DENY', 'reason': 'Founder has not approved override'},
    }

    result = resolver.resolve(test_signals)
    print(result)
