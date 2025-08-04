# action_blocker.py
# Part of HAIL Phase 3 – AI Ethics, Command & Security Logic

from core.shariah_override import ShariahOverride
from core.phase_validator import PhaseValidator

class ActionBlocker:
    def __init__(self):
        self.shariah = ShariahOverride()
        self.phase_validator = PhaseValidator()

    def should_block(self, command):
        # Step 1: Shari’ah Compliance Check
        shariah_result = self.shariah.evaluate_command(command)
        if not shariah_result["allowed"]:
            return {
                "block": True,
                "reason": shariah_result["reason"]
            }

        # Step 2: Blueprint Phase Validity
        phase_result = self.phase_validator.is_valid_phase(command)
        if not phase_result["valid"]:
            return {
                "block": True,
                "reason": phase_result["reason"]
            }

        # If all checks pass
        return {
            "block": False,
            "reason": "Command is allowed."
        }

# Example usage
if __name__ == "__main__":
    blocker = ActionBlocker()
    test = blocker.should_block("Display non-halal content")
    print(test)
