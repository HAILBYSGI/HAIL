# core/query_matcher.py
# Part of HAIL Phase 2 – Memory & Indexing Engine

from __future__ import annotations
import re
from typing import Dict, List, Tuple, Iterable, Optional

Word = str
Label = str  # can be a system name or a phase key like "Phase 3"

def _score(query: str, keywords: Iterable[Word]) -> float:
    """
    Simple word-boundary keyword score in [0,1].
    """
    kws = [k.strip().lower() for k in keywords if k]
    if not kws:
        return 0.0
    q = query.lower()
    hits = 0
    for kw in kws:
        if re.search(rrf"\b{re.escape(kw)}\b", q):
            hits += 1
    return hits / max(1, len(kws))

class QueryMatcher:
    """
    Flexible matcher that can score a free-text query against:
      - phases: {"Phase 2": {"keywords": [...]} }
      - systems: {"memory_store": {"keywords": [...]} }

    Public API:
      - match(query) -> (score: float, label: str)
      - match_query_to_phase(query) -> (phase: str, score: float)   # backward-compatible
      - update_blueprint(map)  # replace internal map
      - add_entry(label, keywords)  # add/extend a label with keywords
    """

    def __init__(self, blueprint_map: Optional[Dict[str, Dict]] = None):
        # Default lightweight signals so it works out-of-the-box
        self.blueprint_map: Dict[str, Dict] = blueprint_map or {
            # Phases (examples)
            "Phase 1": {"keywords": ["founder", "identity", "verification", "protocol", "rules"]},
            "Phase 2": {"keywords": ["memory", "index", "store", "blueprint"]},
            "Phase 3": {"keywords": ["intent", "ethics", "filter", "override", "router"]},
            "Phase 9": {"keywords": ["frontend", "public", "api", "developer", "sandbox"]},
            # Systems (examples)
            "founder_identity": {"keywords": ["founder", "identity", "biometric", "fingerprint", "dna"]},
            "memory_store": {"keywords": ["memory", "save", "load", "persist", "recall"]},
            "system_indexer": {"keywords": ["index", "reindex", "map", "phase", "blueprint"]},
            "halal_task_router": {"keywords": ["route", "task", "assign", "halal"]},
            "deen_activity_monitor": {"keywords": ["activity", "risk", "haram", "shubha", "monitor"]},
            "deen_system_refresher": {"keywords": ["refresh", "maintenance", "purge", "reload", "taqwa"]},
        }

    # ---------------- core matching ----------------
    def match(self, query: str) -> Tuple[float, Label]:
        """
        Return (best_score, best_label) over all entries (phases + systems).
        Used by DynamicPhaseRouter and HalalTaskRouter.
        """
        if not query:
            return 0.0, "unknown"

        best_label: Label = "unknown"
        best_score: float = 0.0

        for label, data in self.blueprint_map.items():
            kws = data.get("keywords", []) or []
            s = _score(query, kws)
            if s > best_score:
                best_score, best_label = s, label

        return best_score, best_label

    # ---------------- phase-only compatibility ----------------
    def match_query_to_phase(self, query: str) -> Tuple[str, float]:
        """
        Backward-compatible: returns (phase, score).
        Scans only entries that look like phases ("Phase X").
        """
        if not query:
            return "", 0.0

        best_phase = ""
        best_score = 0.0
        for label, data in self.blueprint_map.items():
            if not label.lower().startswith("phase "):
                continue
            s = _score(query, data.get("keywords", []))
            if s > best_score:
                best_phase, best_score = label, s

        return best_phase, best_score

    # ---------------- maintenance helpers ----------------
    def update_blueprint(self, blueprint_map: Dict[str, Dict]) -> None:
        """
        Replace the internal map with a new one.
        """
        self.blueprint_map = blueprint_map or {}

    def add_entry(self, label: str, keywords: Iterable[Word]) -> None:
        """
        Add or extend a label with more keywords.
        """
        entry = self.blueprint_map.get(label, {"keywords": []})
        merged = list(entry.get("keywords", [])) + [k for k in keywords if k]
        # de-duplicate while preserving order
        seen, out = set(), []
        for k in merged:
            k = k.strip().lower()
            if k and k not in seen:
                seen.add(k)
                out.append(k)
        entry["keywords"] = out
        self.blueprint_map[label] = entry


# Example usage:
if __name__ == "__main__":
    dummy_data = {
        "Phase 1": {"keywords": ["verification", "identity", "biometrics"]},
        "Phase 2": {"keywords": ["memory", "storage", "query", "match"]},
        "Phase 3": {"keywords": ["ethics", "islam", "filter"]},
        "memory_store": {"keywords": ["memory", "persist", "save", "load"]},
    }

    matcher = QueryMatcher(dummy_data)
    user_query = "how does hail verify identity?"
    score, label = matcher.match(user_query)
    print(f"Best overall match: score={score:.2f}, label={label}")

    phase, pscore = matcher.match_query_to_phase(user_query)
    print(f"Best phase match: {phase} ({pscore:.2f})")
