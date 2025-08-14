# core/system_indexer.py
# Part of HAIL Phase 2 – Memory & Indexing Engine
# Central registry for systems by phase, with lightweight search & routing helpers.

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Tuple, Iterable, Optional
import json
import re


@dataclass
class SystemInfo:
    name: str
    description: str = ""
    keywords: Tuple[str, ...] = ()

    def match_score(self, text: str) -> float:
        """Very light keyword/name/description match (0..1)."""
        if not text:
            return 0.0
        t = text.lower()
        score = 0.0

        # name matches are strongest
        if self.name.lower() in t:
            score += 0.6

        # keyword hits
        hits = 0
        for kw in self.keywords:
            if kw and re.search(rf"\b{re.escape(kw.lower())}\b", t):
                hits += 1
        if self.keywords:
            score += min(0.3, hits / max(1, len(self.keywords)))

        # description fallback
        if self.description and any(w in self.description.lower() for w in t.split()):
            score += 0.1

        return min(1.0, score)


class SystemIndexer:
    def __init__(self):
        # phase -> list[SystemInfo]
        self._systems: Dict[str, List[SystemInfo]] = {}

    # ---------- core CRUD ----------
    def add_system(
        self,
        phase: str,
        system_name: str,
        description: str = "",
        keywords: Optional[Iterable[str]] = None,
    ) -> None:
        info = SystemInfo(
            name=system_name.strip(),
            description=description.strip(),
            keywords=tuple(sorted({*(kw.strip().lower() for kw in (keywords or ())) if kw else ""} - {""}))
        )
        self._systems.setdefault(phase, [])

        # idempotent replace if same name exists in phase
        for i, s in enumerate(self._systems[phase]):
            if s.name.lower() == info.name.lower():
                self._systems[phase][i] = info
                break
        else:
            self._systems[phase].append(info)

    def remove_system(self, phase: str, system_name: str) -> bool:
        lst = self._systems.get(phase, [])
        before = len(lst)
        self._systems[phase] = [s for s in lst if s.name.lower() != system_name.lower()]
        return len(self._systems[phase]) < before

    def reset_index(self) -> None:
        self._systems = {}

    # ---------- bulk indexing ----------
    def index_systems(self, phase_map: Dict[str, Iterable]) -> Dict[str, List[Dict]]:
        """
        Accepts structures like:
          {
            "Phase 3": [
                "shariah_guard",
                {"name": "intent_classifier", "description": "...", "keywords": ["intent","route"]},
            ],
            "Phase 4": [{"name": "device_connector", "description": "IoT bridge"}]
          }
        Returns plain dict for visibility.
        """
        self.reset_index()
        for phase, items in (phase_map or {}).items():
            for item in items:
                if isinstance(item, str):
                    self.add_system(phase, item)
                elif isinstance(item, dict):
                    self.add_system(
                        phase,
                        item.get("name", "").strip() or "unnamed",
                        description=item.get("description", "") or "",
                        keywords=item.get("keywords", ()) or (),
                    )
        return self.get_full_index()

    # ---------- queries ----------
    def get_systems_by_phase(self, phase: str) -> List[Dict]:
        return [asdict(s) for s in self._systems.get(phase, [])]

    def search_system_by_name(self, name_query: str) -> List[Tuple[str, Dict]]:
        results: List[Tuple[str, Dict]] = []
        q = (name_query or "").lower().strip()
        if not q:
            return results
        for phase, systems in self._systems.items():
            for s in systems:
                if q in s.name.lower():
                    results.append((phase, asdict(s)))
        return results

    def get_full_index(self) -> Dict[str, List[Dict]]:
        return {phase: [asdict(s) for s in lst] for phase, lst in self._systems.items()}

    def get_all_systems(self) -> List[str]:
        """Flat list of all system names (used by PhaseValidator)."""
        out: List[str] = []
        for lst in self._systems.values():
            out.extend([s.name for s in lst])
        return out

    def find_system_for_query(self, query: str) -> Optional[str]:
        """
        Used by QueryRedirector: returns best-matching system name or None.
        """
        best_name = None
        best_score = 0.0
        for _, systems in self._systems.items():
            for s in systems:
                sc = s.match_score(query or "")
                if sc > best_score:
                    best_score, best_name = sc, s.name
        return best_name if best_score >= 0.25 else None  # small threshold

    # ---------- (optional) persistence ----------
    def to_json(self) -> str:
        return json.dumps(self.get_full_index(), indent=2, ensure_ascii=False)

    def load_json(self, data: str) -> None:
        obj = json.loads(data or "{}")
        self.reset_index()
        for phase, lst in obj.items():
            for d in lst:
                self.add_system(phase, d.get("name", ""), d.get("description", ""), d.get("keywords", ()))


# ---------- Example usage ----------
if __name__ == "__main__":
    idx = SystemIndexer()
    idx.add_system("Phase 4", "Device Connector", "Connects HAIL to external IoT and digital systems.", ["iot", "bridge", "device"])
    idx.add_system("Phase 4", "Action Core", "Executes commands across approved platforms.", ["executor", "actions"])
    print(idx.get_systems_by_phase("Phase 4"))
    print(idx.search_system_by_name("action"))
    print("Best for 'connect my smart bulb':", idx.find_system_for_query("connect my smart bulb"))
