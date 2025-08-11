from datetime import datetime
from core.shariah_guard import ShariahGuard

class DeenRoutineBalancer:
    def __init__(self):
        self.shariah_guard = ShariahGuard()
        self.required_activities = {
            "Fajr": "05:00",
            "Dhuhr": "13:00",
            "Asr": "16:30",
            "Maghrib": "18:45",
            "Isha": "20:00",
            "Qur'an Recitation": "after Fajr",
            "Dhikr": "after Salah",
            "Du'a": "after Isha",
            "Tawbah": "before sleep"
        }

    def analyze_routine(self, user_log):
        """
        Compares user's daily log with the ideal Islamic schedule and suggests improvements.
        """
        missing = []
        for activity, recommended_time in self.required_activities.items():
            if activity not in user_log or not user_log[activity]:
                missing.append({
                    "activity": activity,
                    "recommended_time": recommended_time,
                    "shariah_compliant": self.shariah_guard.check_routine_compliance(activity)
                })

        return {
            "status": "evaluated",
            "missing_activities": missing,
            "recommendation": "Try to establish a balanced routine based on Qur’an and Sunnah. Prioritize missed prayers and daily Qur’an engagement."
        }

    def suggest_optimal_routine(self):
        """
        Returns a complete Sunnah-aligned daily routine for reference.
        """
        return {
            "routine": self.required_activities,
            "note": "Adjust your schedule around these times to enhance barakah, productivity, and spiritual stability."
        }
