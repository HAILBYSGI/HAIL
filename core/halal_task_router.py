# halal_task_router.py
# Part of HAIL Phase 2 – Memory & Indexing Engine

from core.shariah_guard import ShariahGuard
from core.intent_classifier import IntentClassifier
from core.query_matcher import QueryMatcher

class HalalTaskRouter:
    def __init__(self):
        self.shariah_guard = ShariahGuard()
        self.intent_classifier = IntentClassifier()
        self.query_matcher = QueryMatcher()

    def route_task(self, task_description):
        # Classify the task
        intent = self.intent_classifier.classify(task_description)

        # Check if it violates Islamic law
        if not self.shariah_guard.is_halal(task_description):
            return {
                "status": "rejected",
                "reason": "Task rejected – not Shari’ah-compliant",
                "intent": intent
            }

        # Find the most relevant system or phase to handle it
        match_score, system = self.query_matcher.match(task_description)

        return {
            "status": "accepted",
            "routed_to": system,
            "intent": intent,
            "confidence": match_score
        }

# Example
if __name__ == "__main__":
    router = HalalTaskRouter()
    print(router.route_task("Schedule automatic investment in halal mutual funds"))
