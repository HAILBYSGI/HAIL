from core.quran_filter import QuranFilter
from core.shariah_guard import ShariahGuard

class DeenContextRecommender:
    def __init__(self):
        self.quran_filter = QuranFilter()
        self.shariah_guard = ShariahGuard()

    def recommend(self, current_context):
        """
        Given a user's emotional or situational context, recommend Islamic actions, verses, or habits.
        """
        if not current_context:
            return {"status": "error", "message": "No context provided."}

        context = current_context.lower()

        recommendations = {
            "stress": {
                "verse": "Surah Ar-Ra’d 13:28 – 'Verily, in the remembrance of Allah do hearts find rest.'",
                "action": "Perform 2 rakah nafl prayer and do dhikr (SubhanAllah, Alhamdulillah, Allahu Akbar)."
            },
            "anger": {
                "verse": "Surah Al-Imran 3:134 – 'Those who restrain anger and pardon people.'",
                "action": "Drink water, sit down or lie down, seek refuge with Allah from Shaytan."
            },
            "sadness": {
                "verse": "Surah At-Tawbah 9:51 – 'Nothing will happen to us except what Allah has decreed.'",
                "action": "Recite 'Hasbunallahu wa ni’mal wakeel' and do deep breathing with dhikr."
            },
            "laziness": {
                "verse": "Surah Al-Mulk 67:15 – 'Walk in the paths thereof and eat of His provision.'",
                "action": "Make du'a: 'O Allah, I seek refuge in You from laziness and incapacity.'"
            }
        }

        # Match context
        for key in recommendations:
            if key in context:
                result = recommendations[key]
                break
        else:
            result = {
                "verse": "Surah Al-Isra 17:82 – 'We send down of the Qur'an that which is healing and mercy for the believers.'",
                "action": "Engage in Qur’an recitation and silent dhikr."
            }

        # Validate with filters
        quran_check = self.quran_filter.check_text(result["verse"])
        shariah_check = self.shariah_guard.validate_action(result["action"])

        return {
            "status": "success",
            "context": current_context,
            "recommendation": result,
            "quran_validation": quran_check,
            "shariah_validation": shariah_check
        }
