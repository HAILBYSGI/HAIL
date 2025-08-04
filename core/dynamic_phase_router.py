# dynamic_phase_router.py
# Part of HAIL Phase 2 – Memory & Indexing Engine

from core.query_matcher import QueryMatcher
from core.phase_mapper import PhaseMapper
from core.system_indexer import SystemIndexer

class DynamicPhaseRouter:
    def __init__(self):
        self.query_matcher = QueryMatcher()
        self.phase_mapper = PhaseMapper()
        self.system_indexer = SystemIndexer()

    def route(self, user_query):
        # Match query to blueprint knowledge
        match_score, system = self.query_matcher.match(user_query)

        # Map to the most relevant phase
        phase = self.phase_mapper.map_to_phase(user_query)

        # Route decision logic
        if match_score >= 0.8:
            route = {
                "status": "high-confidence",
                "target_system": system,
                "phase": phase,
                "confidence": match_score
            }
        else:
            route = {
                "status": "low-confidence",
                "message": "Query requires Founder input or fallback logic.",
                "phase": phase,
                "confidence": match_score
            }

        return route

# Example
if __name__ == "__main__":
    router = DynamicPhaseRouter()
    result = router.route("Activate memory reindexing for Phase 6")
    print(result)
