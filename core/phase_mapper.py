# core/phase_mapper.py
# Part of HAIL Phase 2 – Memory & Indexing Engine
# Maps human topics/queries to canonical HAIL phases and validates blueprint dicts.

from __future__ import annotations
from typing import Dict, List, Iterable, Tuple

class PhaseMapper:
    """
    - get_description(phase_key): exact lookup of a phase label
    - find_phase_by_topic(topic): fuzzy-ish search by words inside the phase description
    - map_to_phase(query): route a free-text query to a likely phase key
    - map_phases(blueprint_data): normalize/validate a blueprint mapping {phase -> [systems]}
    - list_phases(): return all canonical phases in order
    """

    # Canonical phase index
    _PHASE_INDEX: Dict[str, str] = {
        "Phase 1":  "Founder Verification & System Rules",
        "Phase 2":  "Memory Core & Index Engine",
        "Phase 3":  "Intent Recognition & Filter Logic",
        "Phase 4":  "Device Integration & Halal Execution",
        "Phase 5":  "Ummah Connectivity & Ethics Layer",
        "Phase 6":  "Self-Learning & Knowledge Mapping",
        "Phase 7":  "Hardware Blueprint & Technical Conversion",
        "Phase 8":  "Security Framework & Final Rights Management",
        "Phase 9":  "Public Interface & Developer Sandbox",
        "Phase 10": "Spiritual Companion & Healing Modes",
        "Phase 11": "AI-Human Hybrid Logic Initiator",
        "Phase 12": "Robotic Host & Embedded Expansion",
        "Phase 13": "Neural Chip Interface & Quantum Readiness",
        "Phase 14": "Dimensional Computing & Ru’h Layer",
        "Phase 15": "Final Day Protocol & Aakhira Response Engine",
    }

    # Lightweight keyword map to route queries to phases (extend as needed)
    _KEYWORDS_TO_PHASE: List[Tuple[Iterable[str], str]] = [
        (("founder", "identity", "verification", "protocol", "rules"), "Phase 1"),
        (("memory", "index", "embedding", "blueprint", "store"), "Phase 2"),
        (("intent", "ethic", "filter", "override", "router"), "Phase 3"),
        (("device", "robot", "execution", "actuator", "integration"), "Phase 4"),
        (("ummah", "network", "connect", "ethics", "compliance"), "Phase 5"),
        (("self-learning", "learn", "knowledge", "mapping"), "Phase 6"),
        (("hardware", "blueprint", "conversion", "electronics"), "Phase 7"),
        (("security", "rights", "access", "integrity"), "Phase 8"),
        (("public", "frontend", "api", "developer", "sandbox"), "Phase 9"),
        (("spiritual", "companion", "healing", "therapy", "deen"), "Phase 10"),
        (("hybrid", "ai-human", "cobotics", "handoff"), "Phase 11"),
        (("robotic", "embedded", "firmware", "edge"), "Phase 12"),
        (("neural", "chip", "bci", "quantum"), "Phase 13"),
        (("dimensional", "ruh", "metaphysics"), "Phase 14"),
        (("final", "aakhira", "day", "protocol"), "Phase 15"),
    ]

    def list_phases(self) -> List[str]:
        """Return canonical phase keys in numeric order."""
        def _num(k: str) -> int:
            try: return int(k.split()[1])
            except Exception: return 999
        return sorted(self._PHASE_INDEX.keys(), key=_num)

    def get_description(self, phase_key: str) -> str:
        """Exact description lookup (case-insensitive key match allowed)."""
        key = self._normalize_phase_key(phase_key)
        return self._PHASE_INDEX.get(key, "Unknown Phase")

    def find_phase_by_topic(self, topic: str) -> str:
        """
        Best-effort matching by scanning descriptions for the topic tokens.
        Returns a Phase key or 'Not Found'.
        """
        if not topic:
            return "Not Found"
        t = topic.lower()
        scores = []
        for k, desc in self._PHASE_INDEX.items():
            desc_l = desc.lower()
            score = sum(1 for w in t.split() if w and w in desc_l)
            scores.append((score, k))
        best = max(scores, key=lambda x: x[0]) if scores else (0, "Not Found")
        return best[1] if best[0] > 0 else "Not Found"

    def map_to_phase(self, query: str) -> str:
        """
        Route a free-text query to a likely Phase using keyword hints.
        Falls back to find_phase_by_topic() and then Phase 3 (filters) as safe default.
        """
        if not query:
            return "Phase 3"
        q = query.lower()

        # 1) Keyword bins
        for keywords, phase in self._KEYWORDS_TO_PHASE:
            if any(k in q for k in keywords):
                return phase

        # 2) Description search
        guess = self.find_phase_by_topic(query)
        if guess != "Not Found":
            return guess

        # 3) Conservative default
        return "Phase 3"

    # ---------- Blueprint utilities ----------

    def map_phases(self, blueprint_data: Dict[str, Iterable[str]]) -> Dict[str, List[str]]:
        """
        Normalize a blueprint map {phase_key -> [systems]}:
        - Accepts variants like 'phase 1', 'PHASE-1', 'Phase_1'
        - Ensures only known Phase keys appear; unknown keys are kept under 'Unmapped'
        - Systems are normalized to strings and deduplicated (preserve order)
        """
        normalized: Dict[str, List[str]] = {k: [] for k in self.list_phases()}
        unmapped: List[str] = []

        for raw_phase, systems in (blueprint_data or {}).items():
            phase_key = self._normalize_phase_key(str(raw_phase))
            sys_list = self._ensure_list_of_str(systems)

            if phase_key in self._PHASE_INDEX:
                normalized[phase_key].extend(self._dedupe_preserve(sys_list))
            else:
                unmapped.extend(self._dedupe_preserve(sys_list))

        # Drop empty lists for cleanliness
        normalized = {k: v for k, v in normalized.items() if v}

        if unmapped:
            normalized["Unmapped"] = self._dedupe_preserve(unmapped)

        return normalized

    # ---------- Helpers ----------

    @staticmethod
    def _dedupe_preserve(items: Iterable[str]) -> List[str]:
        seen, out = set(), []
        for x in items:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out

    @staticmethod
    def _ensure_list_of_str(value: Iterable[str] | str | None) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return [str(x) for x in value if x is not None]

    @staticmethod
    def _normalize_phase_key(key: str) -> str:
        k = key.strip().lower().replace("_", " ").replace("-", " ")
        if k.startswith("phase"):
            parts = k.split()
            if len(parts) >= 2 and parts[1].isdigit():
                return f"Phase {int(parts[1])}"
        # If user passes description, try to find exact match by description substring
        return key if key in PhaseMapper._PHASE_INDEX else key.title()


# Example usage:
if __name__ == "__main__":
    mapper = PhaseMapper()
    print(mapper.get_description("Phase 6"))
    print(mapper.find_phase_by_topic("self-learning"))
    print("Map to phase:", mapper.map_to_phase("please run public API and developer sandbox checks"))
    demo_bp = {
        "phase_1": ["founder_identity", "voice_verification"],
        "PHASE-2": ["memory_store", "system_indexer", "blueprint_auditor"],
        "Unknown": ["mystery_block"]
    }
    print("Normalized:", mapper.map_phases(demo_bp))
