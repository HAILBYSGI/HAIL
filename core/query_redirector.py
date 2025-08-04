# query_redirector.py
# Part of HAIL Phase 2 – Memory & Indexing Engine

from core.phase_mapper import PhaseMapper
from core.system_indexer import SystemIndexer
from core.intent_classifier import IntentClassifier

class QueryRedirector:
    def __init__(self):
        self.phase_mapper = PhaseMapper()
        self.system_indexer = SystemIndexer()
        self.intent_classifier = IntentClassifier()

    def redirect_query(self, query):
        # Step 1: Classify Intent
        intent = self.intent_classifier.classify(query)

        # Step 2: Map to Phase
        phase = self.phase_mapper.map_to_phase(query)

        # Step 3: Index Matching System
        matched_system = self.system_indexer.find_system_for_query(query)

        # Step 4: Decide where to route
        if matched_system:
            return {
                "status": "redirected",
                "intent": intent,
                "phase": phase,
                "system": matched_system
            }
        else:
            return {
                "status": "unresolved",
                "message": "Query could not be redirected. Manual Founder input required.",
                "intent": intent,
                "phase": phase
            }

# Example
if __name__ == "__main__":
    qr = QueryRedirector()
    print(qr.redirect_query("What is the Islamic response to debt?"))
