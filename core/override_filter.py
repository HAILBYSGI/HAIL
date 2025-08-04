# override_filter.py
# Part of HAIL Phase 3 – AI Ethics, Command & Security Logic

class OverrideFilter:
    def __init__(self):
        self.blocked_commands = [
            "override_shariah",
            "disable_quran_filter",
            "ignore_islamic_ethics",
            "force_unverified_action"
        ]

    def is_command_allowed(self, command):
        normalized = command.strip().lower()
        if normalized in self.blocked_commands:
            return False
        return True

    def explain_restriction(self, command):
        if not self.is_command_allowed(command):
            return {
                "status": "BLOCKED",
                "reason": f"The command '{command}' violates Islamic core safeguards and cannot be executed."
            }
        return {
            "status": "ALLOWED",
            "reason": "Command is within Islamic ethical boundaries."
        }

# Example usage
if __name__ == "__main__":
    filter = OverrideFilter()
    result = filter.explain_restriction("override_shariah")
    print(result)
