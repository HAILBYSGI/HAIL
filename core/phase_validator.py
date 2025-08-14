# core/phase_validator.py
# Part of HAIL Phase 3 – AI Ethics, Command & Security Logic

from __future__ import annotations
from typing import Dict, Optional, List

from core.system_indexer import SystemIndexer
from core.phase_mapper import PhaseMapper

class PhaseValidator:
    """
    Validates whether a user's command maps to a known HAIL Phase,
    and (optionally) whether that Phase has indexed systems.
    """
    def __init__(self):
        self.system_indexer = SystemIndexer()
        self.phase_mapper = PhaseMapper()

    def is_valid_phase(self, command: str) -> Dict[str, object]:
        """
        Determine the target Phase for a command and validate it.

        Returns:
            {
              "valid": bool,
              "phase": "Phase X" | None,
              "systems_found": int | None,
              "reason": str | None
            }
        """
        if not command or not isinstance(command, str):
            return {
                "valid": False,
                "phase": None,
                "systems_found": None,
                "reason": "Empty or invalid command."
            }

        # Map free-text command to phase (PhaseMapper upgrade provides map_to_phase)
        phase = self.phase_mapper.map_to_phase(command)

        # Confirm the phase is one of our canonical phases
        known = set(self.phase_mapper.list_phases())
        if phase not in known:
            return {
                "valid": False,
                "phase": phase,
                "systems_found": None,
                "reason": f"Unrecognized or non-canonical phase for command: '{command}'"
            }

        # Optional: check if the indexer has systems for this phase.
        # Support multiple possible APIs gracefully.
        systems_found: Optional[int] = None
        try:
            # Preferred (if implemented):
            if hasattr(self.system_indexer, "get_systems_by_phase"):
                systems = self.system_indexer.get_systems_by_phase(phase)  # type: ignore[attr-defined]
                systems_found = len(systems) if systems is not None else 0
            elif hasattr(self.system_indexer, "get_all_systems"):
                # Fallback: if only a flat list exists, count how many mention the phase key
                all_systems: List[str] = self.system_indexer.get_all_systems()  # type: ignore[attr-defined]
                systems_found = sum(1 for s in (all_systems or []) if isinstance(s, str) and phase.lower() in s.lower())
        except Exception:
            systems_found = None  # keep validation focused on phase existence

        return {
            "valid": True,
            "phase": phase,
            "systems_found": systems_found,
            "reason": None
        }

# Example usage
if __name__ == "__main__":
    validator = PhaseValidator()
    print(validator.is_valid_phase("Track Salah timings"))
    print(validator.is_valid_phase("reindex blueprint memory"))
