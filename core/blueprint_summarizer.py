# blueprint_summarizer.py
# Part of HAIL Phase 2 – Memory & Indexing Engine

class BlueprintSummarizer:
    def __init__(self, blueprint_data):
        self.blueprint_data = blueprint_data

    def summarize_phase(self, phase_name):
        """
        Returns a short summary of the systems in a given phase.
        """
        if phase_name not in self.blueprint_data:
            return f"Phase '{phase_name}' not found in blueprint."
        
        systems = self.blueprint_data[phase_name]
        summary = f"🔹 {phase_name} contains {len(systems)} systems:\n"
        for system in systems:
            summary += f"   • {system.replace('_', ' ').title()}\n"
        return summary.strip()

    def summarize_all(self):
        """
        Summarizes all phases in the blueprint.
        """
        summaries = {}
        for phase in self.blueprint_data:
            summaries[phase] = self.summarize_phase(phase)
        return summaries

# Example usage
if __name__ == "__main__":
    sample_blueprint = {
        "Phase 1": ["founder_identity", "voice_verification", "shariah_guard"],
        "Phase 2": ["memory_store", "system_indexer"]
    }

    summarizer = BlueprintSummarizer(sample_blueprint)
    print(summarizer.summarize_phase("Phase 1"))
    print("---")
    all_summaries = summarizer.summarize_all()
    for phase, summary in all_summaries.items():
        print(summary)
