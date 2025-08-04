# phase_validator.py
# Part of HAIL Phase 3 – AI Ethics, Command & Security Logic

from core.system_indexer import SystemIndexer
from core.phase_mapper import PhaseMapper

class PhaseValidator:
    def __init__(self):
        self.system_indexer = SystemIndexer()
        self.phase_mapper = PhaseMapper()

    def is_valid_phase(self, command):
        phase = self.phase_mapper.get_phase_for_command(command)
        system_list = self.system_indexer.get_all_systems()

        if phase in system_list:
            return {
                "valid": True,
                "phase": phase
            }
        else:
            return {
                "valid": False,
                "reason": f"Phase not recognized for command: {command}"
            }

# Example usage
if __name__ == "__main__":
    validator = PhaseValidator()
    print(validator.is_valid_phase("Track Salah timings"))
