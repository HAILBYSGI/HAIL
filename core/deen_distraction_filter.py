from core.shariah_guard import ShariahGuard

class DeenDistractionFilter:
    def __init__(self):
        self.distraction_keywords = [
            "Netflix", "Gaming", "Social Media", "TikTok", "Reels", 
            "Music (Haram)", "Overuse of phone", "Idle talk", "Browsing"
        ]
        self.shariah_guard = ShariahGuard()

    def detect_distractions(self, activity_log):
        """
        Scans user activities and flags any distractions that reduce focus on Deen.
        """
        flagged = []
        for activity in activity_log:
            for distraction in self.distraction_keywords:
                if distraction.lower() in activity.lower():
                    flagged.append({
                        "distraction": distraction,
                        "activity": activity,
                        "halal_status": self.shariah_guard.check_content(activity)
                    })

        return {
            "status": "filtered",
            "flagged_distractions": flagged,
            "advice": "Reduce distractions that pull you away from Qur’an, Salah, and Islamic growth. Replace with dhikr, Qur’an recitation, or beneficial Islamic learning."
        }

    def recommend_alternatives(self):
        return {
            "alternatives": [
                "Listen to Islamic lectures",
                "Read Qur’an with Tafsir",
                "Join a halaqah or online Islamic class",
                "Do dhikr or tasbeeh",
                "Volunteer for a good cause"
            ],
            "note": "Balance entertainment with Islamic responsibility. HAIL can auto-remind or block excessive distractions if enabled."
        }
