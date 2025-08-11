class ShariahGuidanceRecommender:
    def __init__(self):
        self.guidance_data = {
            "lying": {
                "ruling": "Haram",
                "hadith": "Whoever lies will be recorded as a liar with Allah. – Bukhari",
                "quran": "Surah Al-Baqarah 2:42"
            },
            "interest": {
                "ruling": "Haram",
                "hadith": "The Prophet cursed the one who takes riba, the one who gives it, and the one who records it. – Muslim",
                "quran": "Surah Al-Baqarah 2:275"
            },
            "salah_missed": {
                "ruling": "Severe Warning",
                "hadith": "The difference between us and them is prayer; whoever abandons it has disbelieved. – Tirmidhi",
                "quran": "Surah Maryam 19:59"
            },
            "backbiting": {
                "ruling": "Haram",
                "hadith": "Do you know what backbiting is? It is to mention your brother in a way he dislikes. – Muslim",
                "quran": "Surah Al-Hujurat 49:12"
            }
        }

    def recommend(self, issue_key):
        if issue_key in self.guidance_data:
            return {
                "status": "guidance_found",
                "issue": issue_key,
                "ruling": self.guidance_data[issue_key]["ruling"],
                "hadith": self.guidance_data[issue_key]["hadith"],
                "quran_reference": self.guidance_data[issue_key]["quran"]
            }
        else:
            return {
                "status": "no_guidance",
                "message": f"No direct Shariah ruling found for '{issue_key}'. Please consult a scholar."
            }
