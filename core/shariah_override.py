# core/shariah_override.py
# Part of HAIL Phase 3 – AI Ethics, Command & Security Logic
#
# Bridges high-level override evaluations to QuranFilter.
# - Uses QuranFilter.analyze_text(...) to surface exact matched issues.
# - Returns a consistent shape: {"allowed": bool, "reason": str, "issues": list[str]}
# - Conservative default: if text is empty/None, disallow override.

from __future__ import annotations
from typing import Dict, List
from core.quran_filter import QuranFilter


class ShariahOverride:
    def __init__(self):
        self.quran_filter = QuranFilter()

    def evaluate_command(self, command: str) -> Dict[str, object]:
        """
        Checks if a command violates Islamic boundaries.
        Returns:
          {
            "allowed": bool,
            "reason": str,
            "issues": List[str]   # keywords that triggered restriction (if any)
          }
        """
        text = (command or "").strip()
        if not text:
            return {
                "allowed": False,
                "reason": "Empty command cannot be evaluated.",
                "issues": []
            }

        analysis = self.quran_filter.analyze_text(text)  # {"status": "Halal"|"Restricted", "issues": [...]}

        if analysis.get("status") == "Restricted":
            return {
                "allowed": False,
                "reason": "This command violates Islamic guidelines.",
                "issues": analysis.get("issues", [])
            }

        # Fall back to boolean check for completeness
        if not self.quran_filter.is_halal(text):
            return {
                "allowed": False,
                "reason": "This command violates Islamic guidelines.",
                "issues": analysis.get("issues", [])
            }

        return {
            "allowed": True,
            "reason": "Permissible under Shari’ah.",
            "issues": []
        }


# Example usage
if __name__ == "__main__":
    override = ShariahOverride()
    print(override.evaluate_command("Show inappropriate image"))
    print(override.evaluate_command("Schedule reminder for Fajr"))
