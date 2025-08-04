# founder_preferences.py
# Part of HAIL Phase 2 – Memory & Indexing Engine

class FounderPreferences:
    def __init__(self):
        self.preferences = {
            "response_format": "structured",  # options: structured, concise, hybrid
            "tone": "respectful",             # options: respectful, formal, neutral
            "language": "English",            # options: English, Urdu, Arabic
            "visuals_enabled": True,          # True = allows emoji/symbols
            "use_system_headers": True,       # Whether to display module/system labels
            "default_greeting": "ASSALAM O ALAIKUM!",
            "output_order": "summary_first"   # summary_first or system_first
        }

    def get_preference(self, key):
        return self.preferences.get(key, None)

    def update_preference(self, key, value):
        if key in self.preferences:
            self.preferences[key] = value
            return True
        return False

    def get_all_preferences(self):
        return self.preferences

    def reset_to_defaults(self):
        self.__init__()

# Example usage
if __name__ == "__main__":
    fp = FounderPreferences()
    print(fp.get_preference("tone"))  # respectful
    fp.update_preference("tone", "formal")
    print(fp.get_all_preferences())
