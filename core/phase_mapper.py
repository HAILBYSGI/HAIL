# phase_mapper.py
# Part of HAIL Phase 2 – Memory & Indexing Engine

class PhaseMapper:
    def __init__(self):
        self.phase_index = {
            "Phase 1": "Founder Verification & System Rules",
            "Phase 2": "Memory Core & Index Engine",
            "Phase 3": "Intent Recognition & Filter Logic",
            "Phase 4": "Device Integration & Halal Execution",
            "Phase 5": "Ummah Connectivity & Ethics Layer",
            "Phase 6": "Self-Learning & Knowledge Mapping",
            "Phase 7": "Hardware Blueprint & Technical Conversion",
            "Phase 8": "Security Framework & Final Rights Management",
            "Phase 9": "Public Interface & Developer Sandbox",
            "Phase 10": "Spiritual Companion & Healing Modes",
            "Phase 11": "AI-Human Hybrid Logic Initiator",
            "Phase 12": "Robotic Host & Embedded Expansion",
            "Phase 13": "Neural Chip Interface & Quantum Readiness",
            "Phase 14": "Dimensional Computing & Ru’h Layer",
            "Phase 15": "Final Day Protocol & Aakhira Response Engine"
        }

    def get_description(self, phase_key: str) -> str:
        return self.phase_index.get(phase_key, "Unknown Phase")

    def find_phase_by_topic(self, topic: str) -> str:
        for key, desc in self.phase_index.items():
            if topic.lower() in desc.lower():
                return key
        return "Not Found"

# Example usage:
if __name__ == "__main__":
    mapper = PhaseMapper()
    print(mapper.get_description("Phase 6"))
    print(mapper.find_phase_by_topic("self-learning"))
