# core/query_redirector.py
# Part of HAIL Phase 2 – Memory & Indexing Engine

from __future__ import annotations
from typing import Dict, Optional, Tuple

from core.phase_mapper import PhaseMapper
from core.system_indexer import SystemIndexer
from core.intent_classifier import IntentClassifier
from core.query_matcher import QueryMatcher

class QueryRedirector:
    """
    Given a free-text query, decide the best destination:
      - intent (high level)
      - phase (canonical HAIL phase)
      - system (specific module if we can infer one)
    Falls back gracefully if some subsystem lacks advanced APIs.
    """

    def __init__(self):
        self.phase_mapper = PhaseMapper()
        self.system_indexer = SystemIndexer()
        self.intent_classifier = IntentClassifier()
        self.matcher = QueryMatcher()  # default keyword map available

    def redirect_query(self, query: str) -> Dict[str, object]:
        if not query or not isinstance(query, str):
            return {
                "status": "unresolved",
                "message": "Empty query.",
                "intent": None,
                "phase": None,
                "system": None,
                "confidence": 0.0,
            }

        # 1) Intent
        intent = self.intent_classifier.classify(query)

        # 2) Phase
        phase = self.phase_mapper.map_to_phase(query)

        # 3) System (best-effort)
        system, confidence, reason = self._match_system(query)

        if system:
            return {
                "status": "redirected",
                "intent": intent,
                "phase": phase,
                "system": system,
                "confidence": round(confidence, 3),
                "reason": reason,
            }

        return {
            "status": "unresolved",
            "message": "Query could not be redirected. Manual Founder input required.",
            "intent": intent,
            "phase": phase,
            "system": None,
            "confidence": round(confidence, 3),
            "reason": reason,
        }

    # -------- internals --------
    def _match_system(self, query: str) -> Tuple[Optional[str], float, str]:
        """
        Try multiple strategies to find a concrete system label.
        Returns (system_label|None, confidence, reason).
        """
        # Strategy A: SystemIndexer native method (if it exists)
        try:
            if hasattr(self.system_indexer, "find_system_for_query"):
                sys_label = self.system_indexer.find_system_for_query(query)  # type: ignore[attr-defined]
                if sys_label:
                    return sys_label, 0.90, "SystemIndexer.find_system_for_query matched."
        except Exception:
            pass

        # Strategy B: Use QueryMatcher over its blueprint map
        try:
            score, label = self.matcher.match(query)
            # Heuristic: consider it a system if label doesn't look like "Phase X"
            if label and not label.lower().startswith("phase "):
                return label, float(score), "QueryMatcher matched a system label."
        except Exception:
            pass

        # Strategy C: nothing matched
        return None, 0.0, "No matching system found."

# Example
if __name__ == "__main__":
    qr = QueryRedirector()
    print(qr.redirect_query("What is the Islamic response to debt?"))
