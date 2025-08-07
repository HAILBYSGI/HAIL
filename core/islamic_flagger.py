# core/islamic_flagger.py

class IslamicFlagger:
    def __init__(self):
        self.flagged_items = []

    def evaluate(self, content, context=""):
        flags = []

        if any(term in content.lower() for term in ["music", "gambling", "astrology", "nudity", "dating"]):
            flags.append("Potential Haram content")

        if "shaytan" in content.lower() or "devil" in content.lower():
            flags.append("Shirk-adjacent mention")

        if "pray later" in content.lower() or "skip fasting" in content.lower():
            flags.append("Ibadah inconsistency alert")

        if flags:
            flagged_entry = {
                "content": content,
                "context": context,
                "flags": flags
            }
            self.flagged_items.append(flagged_entry)
            return {
                "flagged": True,
                "entry": flagged_entry
            }

        return {
            "flagged": False,
            "message": "No concern detected"
        }

    def get_all_flags(self):
        return self.flagged_items
