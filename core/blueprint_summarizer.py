# core/blueprint_summarizer.py
# Part of HAIL Phase 2 – Memory & Indexing Engine (Upgraded)

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple

try:
    from core.action_logger import ActionLogger
except Exception:  # pragma: no cover
    ActionLogger = None  # type: ignore


@dataclass
class PhaseSummary:
    phase: str
    count: int
    systems: List[str]
    description: str = ""
    notes: List[str] = None  # e.g., ["empty_phase"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase,
            "count": self.count,
            "systems": list(self.systems),
            "description": self.description,
            "notes": list(self.notes or []),
        }

    def to_text(self) -> str:
        bullet = "\n".join([f"   • {s.replace('_',' ').title()}" for s in self.systems]) if self.systems else "   • (none)"
        desc = f"\n   – {self.description}" if self.description else ""
        return f"🔹 {self.phase} contains {self.count} system(s):\n{bullet}{desc}"


@dataclass
class BlueprintSummaryReport:
    total_phases: int
    total_systems: int
    phases: List[PhaseSummary]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_phases": self.total_phases,
            "total_systems": self.total_systems,
            "phases": [p.to_dict() for p in self.phases],
        }

    def to_text(self) -> str:
        lines = [f"📘 Blueprint Summary — {self.total_phases} phases, {self.total_systems} systems"]
        lines += [p.to_text() for p in self.phases]
        return "\n\n".join(lines)


class BlueprintSummarizer:
    """
    Summarizes blueprint phases for display and auditing.

    Accepts blueprint in either form:
      {"Phase 1": ["founder_identity", "voice_verification"]}
      {"Phase 3.50": {"systems": ["deen_system_refresher"], "desc": "maintenance & ethics"}}
    """

    def __init__(self, blueprint_data: Dict[str, Any], *, action_logger: Optional["ActionLogger"] = None) -> None:
        self.bp = blueprint_data
        self.log = action_logger

    # -------- helpers --------

    def _extract(self, phase: str, payload: Any) -> Tuple[List[str], str, List[str]]:
        """Return (systems, description, notes)."""
        notes: List[str] = []
        if isinstance(payload, dict):
            systems = payload.get("systems") or payload.get("modules") or []
            desc = payload.get("desc") or payload.get("description") or ""
        else:
            systems = payload
            desc = ""
        # normalize to list[str]
        systems = [s for s in (systems or []) if isinstance(s, str)]
        if not systems:
            notes.append("empty_phase")
        return systems, desc, notes

    # -------- public API --------

    def summarize_phase(self, phase_name: str) -> str:
        """Pretty text summary for a single phase (backward compatible)."""
        if phase_name not in self.bp:
            return f"Phase '{phase_name}' not found in blueprint."
        systems, desc, _ = self._extract(phase_name, self.bp[phase_name])
        ps = PhaseSummary(phase=phase_name, count=len(systems), systems=systems, description=desc)
        return ps.to_text()

    def summarize_phase_structured(self, phase_name: str) -> Dict[str, Any]:
        """Structured summary for one phase."""
        if phase_name not in self.bp:
            return {"error": f"Phase '{phase_name}' not found"}
        systems, desc, notes = self._extract(phase_name, self.bp[phase_name])
        ps = PhaseSummary(phase=phase_name, count=len(systems), systems=systems, description=desc, notes=notes)
        return ps.to_dict()

    def summarize_all(self) -> Dict[str, str]:
        """
        Backward-compatible dict of {phase: text}. Use report() for structured output.
        """
        out: Dict[str, str] = {}
        for phase in self.bp:
            out[phase] = self.summarize_phase(phase)
        # optional: log a compact summary line
        if self.log:
            try:
                self.log.log(
                    action_type="BlueprintSummary",
                    decision="INFO",
                    module="blueprint_summarizer",
                    status="Success",
                    reason="summarize_all(text)",
                    context={"phases": len(self.bp)},
                )
            except Exception:
                pass
        return out

    def report(self) -> BlueprintSummaryReport:
        """
        Structured report with totals and per-phase details.
        """
        phases: List[PhaseSummary] = []
        total_systems = 0
        for phase, payload in self.bp.items():
            systems, desc, notes = self._extract(phase, payload)
            total_systems += len(systems)
            phases.append(PhaseSummary(phase=phase, count=len(systems), systems=systems, description=desc, notes=notes))

        rep = BlueprintSummaryReport(total_phases=len(phases), total_systems=total_systems, phases=phases)

        if self.log:
            try:
                self.log.log(
                    action_type="BlueprintSummary",
                    decision="INFO",
                    module="blueprint_summarizer",
                    status="Success",
                    reason="report(structured)",
                    context=rep.to_dict(),
                )
            except Exception:
                pass

        return rep
        

# Example usage
if __name__ == "__main__":
    # from core.action_logger import ActionLogger
    # logger = ActionLogger(also_print=True)
    sample_blueprint = {
        "Phase 1": ["founder_identity", "voice_verification", "shariah_guard"],
        "Phase 2": {"systems": ["memory_store", "system_indexer"], "desc": "Memory & Indexing Engine"},
        "Phase 3.49": {"systems": ["deen_activity_monitor"], "desc": "Real-time Deen activity events"},
    }

    summarizer = BlueprintSummarizer(sample_blueprint)  # or BlueprintSummarizer(sample_blueprint, action_logger=logger)
    print(summarizer.summarize_phase("Phase 1"))
    print("---")
    rep = summarizer.report()
    print(rep.to_text())
