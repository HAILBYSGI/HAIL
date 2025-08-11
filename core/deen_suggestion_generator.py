class DeenSuggestionGenerator:
    def __init__(self):
        self.suggestions_map = {
            "anger": [
                "Make wudu (ablution) to cool your anger – Hadith",
                "Say: A'udhu billahi min ash-shaytan ir-rajim (I seek refuge with Allah from the accursed devil)",
                "Change your physical position – sit if you are standing"
            ],
            "depression": [
                "Increase dhikr (remembrance) of Allah",
                "Recite Surah Ad-Duha – the Prophet ﷺ received it during distress",
                "Establish regular prayer – Allah says: 'Indeed, prayer restrains from shameful and unjust deeds' (29:45)"
            ],
            "laziness": [
                "Recite the dua: 'O Allah, I seek refuge in You from laziness and helplessness'",
                "Break tasks into smaller parts and begin with Bismillah",
                "Remember the reward of even small efforts in the path of Allah"
            ],
            "missed_fajr": [
                "Sleep early and avoid screen exposure before bed",
                "Set multiple alarms and ask a family member to wake you",
                "Make sincere dua for Allah to make you of those who establish prayer"
            ]
        }

    def suggest(self, issue):
        if issue in self.suggestions_map:
            return {
                "status": "suggestions_found",
                "issue": issue,
                "suggestions": self.suggestions_map[issue]
            }
        else:
            return {
                "status": "no_suggestion_found",
                "message": f"No predefined Deeni suggestions for '{issue}'. Consider adding to database."
            }
