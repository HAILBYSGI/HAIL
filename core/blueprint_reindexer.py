# core/blueprint_reindexer.py
# Part of HAIL Phase 2 – Memory & Indexing Engine (Upgraded)

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple

from core.system_indexer import SystemIndexer
from core.phase_mapper import PhaseMapper

try:
    from core.action_logger import ActionLogger
except Exception:  # pragma: no cover
    ActionLogger = None  # type: ignore


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PhaseDetail:
    phase: str
    systems_in: int
    systems_indexed: int
    notes: List[str] = field(default_factory=list)


@dataclass
class ReindexReport:
    started_at: str
    finished_at: str
    status: str            # "REINDEXED" | "DRY_RUN" | "FAILED"
    total_phases: int
    total_systems: int
    phases: List[PhaseDetail] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "total_phases": self.total_phases,
            "total_systems": self.total_systems,
            "phases": [asdict(p) for p in self.phases],
            "errors": list(self.errors),
            "meta": dict(self.meta),
        }


class BlueprintReindexer:
    """
    Rebuilds the searchable system index from a HAIL blueprint mapping.

    Parameters
    ----------
    blueprint_data : Dict[str, Any]
        Recommended shapes:
          {"Phase 1": ["founder_identity", "voice_verification"], ...}
          {"Phase 3.49": {"systems": ["deen_activity_monitor", ...]}, ...}

    action_logger : ActionLogger | None
        Optional structured logger; if provided, writes JSONL entries.

    mission_log_sink : callable(dict) -> None | None
        Optional sink that mirrors summary into DeenMissionLog.
        Expected mapping in sink:
            mission_log.append(
                actor_id="system:reindexer", activity="blueprint_reindex", verdict=..., ...
            )
    """

    def __init__(
        self,
        blueprint_data: Dict[str, Any],
        *,
        action_logger: Optional["ActionLogger"] = None,
        mission_log_sink: Optional[callable] = None,
    ) -> None:
        self.blueprint_data = blueprint_data
        self.indexer = SystemIndexer()
        self.phase_mapper = PhaseMapper()
        self.log = action_logger
        self.mission_log_sink = mission_log_sink

    # ----------------- public API -----------------

    def reindex_blueprint(
        self,
        *,
        dry_run: bool = False,
        clear_before: bool = False,
        extras: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Fully re-scan and (optionally) re-index the current blueprint memory.

        Args:
            dry_run: If True, do not write to the indexer; just compute mappings.
            clear_before: If True, attempt to clear the index before indexing (if supported by SystemIndexer).
            extras: arbitrary metadata to be attached to the report.

        Returns:
            dict summary report (ReindexReport.to_dict()).
        """
        started = _utc_iso()
        errors: List[str] = []
        phase_details: List[PhaseDetail] = []
        total_systems = 0
        status = "DRY_RUN" if dry_run else "REINDEXED"

        # Basic validation of blueprint shape
        valid, validation_errors = self._validate_blueprint(self.blueprint_data)
        if not valid:
            finished = _utc_iso()
            report = ReindexReport(
                started_at=started,
                finished_at=finished,
                status="FAILED",
                total_phases=0,
                total_systems=0,
                phases=[],
                errors=validation_errors,
                meta={"dry_run": dry_run, "clear_before": clear_before} | (extras or {}),
            )
            self._write_logs(report)
            return report.to_dict()

        try:
            # Map phases -> systems using PhaseMapper
            phase_mappings = self.phase_mapper.map_phases(self.blueprint_data)
            # Normalize into {phase: [systems...]}
            normalized = self._normalize_mappings(phase_mappings)

            # Indexing step
            if not dry_run:
                if clear_before and hasattr(self.indexer, "clear_all"):
                    try:
                        self.indexer.clear_all()  # type: ignore[attr-defined]
                    except Exception as e:
                        errors.append(f"clear_all failed: {type(e).__name__}: {e}")

                # index phase-by-phase to gather details
                for phase, systems in normalized.items():
                    systems_in = len(systems)
                    try:
                        indexed_list = self.indexer.index_systems({phase: systems})
                        # Some indexers may return dicts/lists; normalize
                        systems_indexed = len(indexed_list) if isinstance(indexed_list, list) else len(systems)
                        total_systems += systems_indexed
                        phase_details.append(PhaseDetail(phase=phase, systems_in=systems_in, systems_indexed=systems_indexed))
                    except Exception as e:
                        errors.append(f"Index error in {phase}: {type(e).__name__}: {e}")
                        phase_details.append(PhaseDetail(phase=phase, systems_in=systems_in, systems_indexed=0, notes=["index_error"]))
            else:
                # dry-run: no writes; just count
                for phase, systems in normalized.items():
                    systems_in = len(systems)
                    total_systems += systems_in
                    phase_details.append(PhaseDetail(phase=phase, systems_in=systems_in, systems_indexed=0, notes=["dry_run"]))

            finished = _utc_iso()
            report = ReindexReport(
                started_at=started,
                finished_at=finished,
                status=status if not errors else "REINDEXED_WITH_WARNINGS",
                total_phases=len(normalized),
                total_systems=total_systems,
                phases=phase_details,
                errors=errors,
                meta={"dry_run": dry_run, "clear_before": clear_before} | (extras or {}),
            )
            self._write_logs(report)
            return report.to_dict()

        except Exception as e:
            finished = _utc_iso()
            report = ReindexReport(
                started_at=started,
                finished_at=finished,
                status="FAILED",
                total_phases=0,
                total_systems=0,
                phases=[],
                errors=[f"{type(e).__name__}: {e}"],
                meta={"dry_run": dry_run, "clear_before": clear_before} | (extras or {}),
            )
            self._write_logs(report)
            return report.to_dict()

    # ----------------- helpers -----------------

    def _validate_blueprint(self, bp: Dict[str, Any]) -> Tuple[bool, List[str]]:
        errors: List[str] = []
        if not isinstance(bp, dict) or not bp:
            errors.append("Blueprint must be a non-empty dict of phases.")
            return False, errors
        for phase, payload in bp.items():
            if not isinstance(phase, str) or not phase.strip().lower().startswith("phase"):
                errors.append(f"Invalid phase key: {phase!r}")
            if not isinstance(payload, (list, dict)):
                errors.append(f"Phase {phase}: value must be list or dict")
        return (len(errors) == 0), errors

    def _normalize_mappings(self, mapped: Dict[str, Any]) -> Dict[str, List[str]]:
        """
        Normalize PhaseMapper output into: {phase: [system_name, ...]}
        Accepts either:
          - { "Phase X": ["mod1","mod2"] }
          - { "Phase X": {"systems": ["mod1","mod2"], ...} }
        """
        out: Dict[str, List[str]] = {}
        for phase, value in mapped.items():
            if isinstance(value, dict):
                systems = value.get("systems") or value.get("modules") or []
            else:
                systems = value
            # ensure list[str]
            systems = [s for s in systems if isinstance(s, str)]
            out[phase] = systems
        return out

    def _write_logs(self, report: ReindexReport) -> None:
        # ActionLogger sink
        if self.log:
            decision = "APPROVED" if report.status in ("REINDEXED", "DRY_RUN") else ("WARN" if not report.errors else "ERROR")
            self.log.log(
                action_type="BlueprintReindex",
                decision=decision,
                module="blueprint_reindexer",
                status="Success" if decision in ("APPROVED", "WARN") else "Failure",
                reason=f"Reindex {report.status}",
                context=report.to_dict(),
            )

        # MissionLog sink (optional)
        if self.mission_log_sink:
            try:
                verdict = "halal" if report.status in ("REINDEXED", "DRY_RUN", "REINDEXED_WITH_WARNINGS") else "shubha"
                score = 0.04 if verdict == "halal" else 0.5
                self.mission_log_sink(
                    {
                        "actor_id": "system:reindexer",
                        "activity": "blueprint_reindex",
                        "verdict": verdict,
                        "score": score,
                        "reasons": [f"Status: {report.status}", f"Phases: {report.total_phases}", f"Systems: {report.total_systems}"],
                        "tags": ["index", "blueprint", "maintenance"],
                        "payload": report.to_dict(),
                    }
                )
            except Exception:
                pass


# Example usage
if __name__ == "__main__":
    from core.action_logger import ActionLogger  # type: ignore

    dummy_blueprint = {
        "Phase 1": ["founder_identity", "voice_verification"],
        "Phase 2": {"systems": ["memory_store", "system_indexer", "blueprint_auditor"]},
        "Phase 3.49": {"systems": ["deen_activity_monitor"]},
    }

    reindexer = BlueprintReindexer(dummy_blueprint, action_logger=ActionLogger(also_print=True))
    print(reindexer.reindex_blueprint(dry_run=True))     # preview only
    print(reindexer.reindex_blueprint(clear_before=False))
