# shariah_override.py
# Part of HAIL Phase 3 – AI Ethics, Command & Security Logic

from core.quran_filter import QuranFilter

class ShariahOverride:
    def __init__(self):
        self.quran_filter = QuranFilter()

    def evaluate_command(self, command):
        """
        Check if the command violates Islamic boundaries.
        """
        if self.quran_filter.is_forbidden(command):
            return {
                "allowed": False,
                "reason": "This command violates Islamic guidelines."
            }

        return {
            "allowed": True,
            "reason": "Permissible under Shari’ah."
        }

# Example usage
if __name__ == "__main__":
    override = ShariahOverride()
    print(override.evaluate_command("Show inappropriate image"))
