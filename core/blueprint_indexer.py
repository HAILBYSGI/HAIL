# blueprint_indexer.py
# Part of HAIL Phase 2 – Memory & Indexing Engine

import json
from typing import Dict, Any
from pathlib import Path

class BlueprintIndexer:
    def __init__(self, memory_path: str = "hail_data/blueprints.json"):
        self.memory_path = memory_path
        self._ensure_file()

    def _ensure_file(self):
        path = Path(self.memory_path)
        if not path.parent.exists():
            path.parent.mkdir(parents=True)
        if not path.exists():
            with open(self.memory_path, 'w') as f:
                json.dump({}, f)

    def load_blueprints(self) -> Dict[str, Any]:
        try:
            with open(self.memory_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            return {}

    def save_blueprint(self, phase_id: str, blueprint_data: Dict[str, Any]) -> bool:
        try:
            data = self.load_blueprints()
            data[phase_id] = blueprint_data
            with open(self.memory_path, 'w') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            return False

    def get_blueprint(self, phase_id: str) -> Dict[str, Any]:
        data = self.load_blueprints()
        return data.get(phase_id, {})

    def list_all_phases(self) -> list:
        data = self.load_blueprints()
        return list(data.keys())

# Example usage:
if __name__ == "__main__":
    bi = BlueprintIndexer()
    example_data = {"purpose": "Phase 2.2 test", "modules": ["storage", "access"]}
    bi.save_blueprint("Phase_2.2", example_data)
    print(bi.list_all_phases())
