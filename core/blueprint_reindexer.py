# blueprint_reindexer.py
# Part of HAIL Phase 2 – Memory & Indexing Engine

from core.system_indexer import SystemIndexer
from core.phase_mapper import PhaseMapper

class BlueprintReindexer:
    def __init__(self, blueprint_data):
        self.blueprint_data = blueprint_data
        self.indexer = SystemIndexer()
        self.phase_mapper = PhaseMapper()

    def reindex_blueprint(self):
        """
        Fully re-scans and re-indexes the current blueprint memory.
        """
        phase_mappings = self.phase_mapper.map_phases(self.blueprint_data)
        indexed = self.indexer.index_systems(phase_mappings)
        return {
            "status": "REINDEXED",
            "total_systems": len(indexed),
            "phases": list(phase_mappings.keys())
        }

# Example usage
if __name__ == "__main__":
    dummy_blueprint = {
        "Phase 1": ["founder_identity", "voice_verification"],
        "Phase 2": ["memory_store", "system_indexer", "blueprint_auditor"]
    }

    reindexer = BlueprintReindexer(dummy_blueprint)
    output = reindexer.reindex_blueprint()
    print(output)
