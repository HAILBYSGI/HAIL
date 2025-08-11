from core.deen_suggestion_generator import DeenSuggestionGenerator
from core.quran_filter import QuranFilter
from core.shariah_guard import ShariahGuard

class DeenAIAdvisor:
    def __init__(self):
        self.suggester = DeenSuggestionGenerator()
        self.quran_filter = QuranFilter()
        self.shariah_guard = ShariahGuard()

    def advise(self, user_query, context=None):
        """
        Main advisory interface: determines deen-related advice based on context or keyword.
        """
        if not user_query:
            return {"status": "error", "message": "Query is empty."}

        issue = self.detect_issue(user_query)
        if issue:
            suggestion = self.suggester.suggest(issue)
        else:
            suggestion = {"status": "unknown", "message": "No specific issue detected."}

        # Filter suggestion through Qur’an and Shariah layers
        quran_check = self.quran_filter.check_text(user_query)
        shariah_check = self.shariah_guard.validate_action(user_query)

        return {
            "status": "advice_ready",
            "original_query": user_query,
            "identified_issue": issue,
            "suggestion": suggestion,
            "quran_validation": quran_check,
            "shariah_validation": shariah_check
        }

    def detect_issue(self, text):
        """
        Basic keyword detection. In production, upgrade with NLP-based emotion/context parser.
        """
        keywords = {
            "anger": ["angry", "furious", "mad"],
            "depression": ["depressed", "hopeless", "sad"],
            "laziness": ["lazy", "unmotivated", "tired"],
            "missed_fajr": ["missed fajr", "couldn't wake", "missed prayer"]
        }

        text_lower = text.lower()
        for issue, keys in keywords.items():
            if any(key in text_lower for key in keys):
                return issue
        return None
