# system_indexer.py
# Part of HAIL Phase 2 – Memory & Indexing Engine

class SystemIndexer:
    def __init__(self):
        self.systems = {}

    def add_system(self, phase: str, system_name: str, description: str):
        if phase not in self.systems:
            self.systems[phase] = []
        self.systems[phase].append({
            "name": system_name,
            "description": description
        })

    def get_systems_by_phase(self, phase: str):
        return self.systems.get(phase, [])

    def search_system_by_name(self, name_query: str):
        results = []
        for phase, systems in self.systems.items():
            for system in systems:
                if name_query.lower() in system["name"].lower():
                    results.append((phase, system))
        return results

    def get_full_index(self):
        return self.systems

# Example usage
if __name__ == "__main__":
    indexer = SystemIndexer()
    indexer.add_system("Phase 4", "Device Connector", "Connects HAIL to external IoT and digital systems.")
    indexer.add_system("Phase 4", "Action Core", "Executes commands across approved platforms.")
    print(indexer.get_systems_by_phase("Phase 4"))
    print(indexer.search_system_by_name("action"))
