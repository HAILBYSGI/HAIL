# query_matcher.py
# Part of HAIL Phase 2 – Memory & Indexing Engine

import re
from typing import Dict, List, Tuple

class QueryMatcher:
    def __init__(self, blueprint_map: Dict[str, Dict]):
        """
        blueprint_map should be a dictionary where keys are phase names,
        and values are dicts containing 'keywords' or 'description' fields
        """
        self.blueprint_map = blueprint_map

    def match_query_to_phase(self, query: str) -> Tuple[str, float]:
        query = query.lower()
        best_match = ("", 0.0)

        for phase, data in self.blueprint_map.items():
            keywords = data.get("keywords", [])
            match_score = self._calculate_match_score(query, keywords)
            if match_score > best_match[1]:
                best_match = (phase, match_score)

        return best_match

    def _calculate_match_score(self, query: str, keywords: List[str]) -> float:
        matches = sum(1 for kw in keywords if re.search(r'\b' + re.escape(kw.lower()) + r'\b', query))
        return matches / len(keywords) if keywords else 0.0

# Example usage:
if __name__ == "__main__":
    dummy_data = {
        "Phase_1": {"keywords": ["verification", "identity", "biometrics"]},
        "Phase_2": {"keywords": ["memory", "storage", "query", "match"]},
        "Phase_3": {"keywords": ["ethics", "Islam", "filter"]}
    }

    matcher = QueryMatcher(dummy_data)
    user_query = "how does hail verify identity?"
    match = matcher.match_query_to_phase(user_query)
    print(f"Best match: {match}")
