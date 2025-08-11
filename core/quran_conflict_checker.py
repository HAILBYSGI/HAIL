class QuranConflictChecker:
    def __init__(self):
        # Simulated database of Qur'anic values and principles
        self.quran_values = {
            "truthfulness": "Surah Al-Baqarah 2:42",
            "justice": "Surah An-Nahl 16:90",
            "no compulsion in religion": "Surah Al-Baqarah 2:256",
            "respect for parents": "Surah Al-Isra 17:23"
        }

    def check_conflict(self, action_description):
        violations = []

        # Simple keyword-based example for demonstration
        if "lie" in action_description.lower():
            violations.append({
                "violation": "Truthfulness",
                "reference": self.quran_values["truthfulness"]
            })

        if "unjust" in action_description.lower() or "oppress" in action_description.lower():
            violations.append({
                "violation": "Justice",
                "reference": self.quran_values["justice"]
            })

        if "force religion" in action_description.lower():
            violations.append({
                "violation": "No compulsion in religion",
                "reference": self.quran_values["no compulsion in religion"]
            })

        if "disobey parents" in action_description.lower():
            violations.append({
                "violation": "Respect for Parents",
                "reference": self.quran_values["respect for parents"]
            })

        if violations:
            return {
                "status": "conflict_detected",
                "conflicts": violations
            }
        else:
            return {
                "status": "no_conflict",
                "message": "No Qur'anic conflict detected."
            }
