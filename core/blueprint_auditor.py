# core/blueprint_auditor.py
# Part of HAIL – Memory & Indexing + Deen Compliance
from __future__ import annotations

import re
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any

try:
    from core.action_logger import ActionLogger
except Exception:  # pragma: no cover
    ActionLogger = None  # type: ignore


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_PHASE_RE = re.compile(r"^\s*Phase\s+(\d+(?:\.\d+)?)\s*$", re.IGNORECASE)


@dataclass
class CompletenessReport:
    expected: List[str]
    uploaded: List[str]
    missing: List[str]
    status: str  # "COMPLETE" | "INCOMPLETE"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ShariahIssue:
    phase: str
    severity: str  # "low" | "medium" | "high" | "critical"
    term: str
    note: str
    evidence: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BlueprintAuditReport:
    timestamp: str
    completeness: CompletenessReport
    shariah_issues: List[ShariahIssue] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "completeness": self.completeness.to_dict(),
            "shariah_issues": [i.to_dict() for i in self.shariah_issues],
            "recommendations": list(self.recommendations),
        }


class BlueprintAuditor:
    """
    Audits the HAIL blueprint for:
      1) Phase completeness (supports 'Phase 1', 'Phase 3.50', etc.)
      2) Shari'ah keyword scanning with severities and evidence

    Optional sinks:
      - action_logger (JSONL via ActionLogger)
      - mission_log_sink: callable(dict) -> None  (maps to DeenMissionLog.append)
    """

    # Terms are examples; refine per your fiqh board
    _TERM_RULES: List[Tuple[re.Pattern, str, str]] = [
        # pattern, severity, note
        (re.compile(r"\bharam\b", re.IGNORECASE), "high", "Potentially impermissible reference."),
        (re.compile(r"\briba\b|\binterest\b", re.IGNORECASE), "high", "Riba/interest indicators."),
        (re.compile(r"\bnud(e|ity)\b|\bexplicit\b", re.IGNORECASE), "high", "Modesty violation risk."),
        (re.compile(r"\blying\b|\bfalsehood\b", re.IGNORECASE), "critical", "Truth violation indicator."),
        (re.compile(r"\bshirk\b", re.IGNORECASE), "critical", "Shirk indicator."),
        (re.compile(r"\bunauthorized\b|\bbackdoor\b", re.IGNORECASE), "medium", "Security / authority concern."),
        (re.compile(r"\bbackbit(ing|e)\b|\bslander\b", re.IGNORECASE), "medium", "Gheebah/namīmah risk."),
    ]

    def __init__(
        self,
        *,
        action_logger: Optional["ActionLogger"] = None,
        mission_log_sink: Optional[callable] = None,
        expected_phases: Optional[List[str]] = None,
    ) -> None:
        self.phases: Dict[str, str] = {}
        self.action_logger = action_logger
        self.mission_log_sink = mission_log_sink
        # If not provided, default to Phase 1..Phase 20 (can be overridden)
        self.expected_phases = expected_phases or [f"Phase {i}" for i in range(1, 21)]

    # ---------- Load / Configure ----------

    def set_expected_phases(self, phases: List[str]) -> None:
        """Override expected phases (e.g., include 'Phase 3.49', 'Phase 3.50', ...)."""
        self.expected_phases = phases

    def load_blueprint(self, blueprint_dict: Dict[str, str]) -> None:
        """
        blueprint_dict format: {
            "Phase 1": "Verification & Identity Layer",
            "Phase 3.49": "Deen Activity Monitor",
            ...
        }
        """
        self.phases = blueprint_dict

    # ---------- Audits ----------

    def _normalize_phase_keys(self, keys: List[str]) -> List[str]:
        """Keep original keys but ensure they match 'Phase N[.M]' form."""
        out = []
        for k in keys:
            m = _PHASE_RE.match(k.strip())
            out.append(k if m else k.strip())
        return out

    def audit_completeness(self, *, expected: Optional[List[str]] = None) -> CompletenessReport:
        expected_list = self._normalize_phase_keys(expected or self.expected_phases)
        uploaded_list = self._normalize_phase_keys(list(self.phases.keys()))
        missing = [p for p in expected_list if p not in uploaded_list]
        status = "COMPLETE" if not missing else "INCOMPLETE"
        report = CompletenessReport(expected=expected_list, uploaded=uploaded_list, missing=missing, status=status)

        if self.action_logger:
            self.action_logger.log(
                action_type="BlueprintAudit",
                decision="APPROVED" if status == "COMPLETE" else "WARN",
                module="blueprint_auditor",
                status="Success",
                reason=f"Completeness: {status}",
                context={"missing": missing, "uploaded": uploaded_list, "expected": expected_list},
            )

        if self.mission_log_sink:
            try:
                verdict = "halal" if status == "COMPLETE" else "shubha"
                self.mission_log_sink(
                    {
                        "actor_id": "system:auditor",
                        "activity": "blueprint_completeness",
                        "verdict": verdict,
                        "score": 0.02 if status == "COMPLETE" else 0.45,
                        "reasons": [f"Completeness is {status}"],
                        "tags": ["audit", "blueprint", "completeness"],
                        "payload": asdict(report),
                    }
                )
            except Exception:
                pass

        return report

    def check_shariah_keywords(self) -> List[ShariahIssue]:
        issues: List[ShariahIssue] = []
        for phase, content in self.phases.items():
            text = f"{phase} {content}".lower()
            for pat, severity, note in self._TERM_RULES:
                m = pat.search(text)
                if not m:
                    continue
                # capture a short evidence snippet
                start = max(m.start() - 20, 0)
                end = min(m.end() + 20, len(text))
                snippet = text[start:end]
                issues.append(ShariahIssue(phase=phase, severity=severity, term=m.group(0), note=note, evidence=snippet))

        if issues and self.action_logger:
            self.action_logger.log(
                action_type="BlueprintAudit",
                decision="WARN",
                module="blueprint_auditor",
                status="Success",
                reason="Shari'ah keyword flags present",
                context={"count": len(issues)},
                meta={"severity_max": max((i.severity for i in issues), default="low")},
            )

        if issues and self.mission_log_sink:
            try:
                self.mission_log_sink(
                    {
                        "actor_id": "system:auditor",
                        "activity": "blueprint_shariah_scan",
                        "verdict": "shubha",
                        "score": 0.55,
                        "reasons": [f"{len(issues)} potential Shari'ah flags"],
                        "tags": ["audit", "blueprint", "shariah_scan"],
                        "payload": [i.to_dict() for i in issues],
                    }
                )
            except Exception:
                pass

        return issues

    def run_full_audit(self, *, expected: Optional[List[str]] = None) -> BlueprintAuditReport:
        completeness = self.audit_completeness(expected=expected)
        issues = self.check_shariah_keywords()

        recs: List[str] = []
        if completeness.status != "COMPLETE":
            recs.append("Upload the missing phases to reach a COMPLETE blueprint.")
        if any(i.severity in ("high", "critical") for i in issues):
            recs.append("Resolve critical/high Shari'ah flags immediately (consult fiqh board).")
        if issues and not any(i.severity in ("high", "critical") for i in issues):
            recs.append("Review medium/low flags and annotate why they are acceptable.")

        report = BlueprintAuditReport(
            timestamp=_utc_iso(),
            completeness=completeness,
            shariah_issues=issues,
            recommendations=recs,
        )

        # Final log line
        if self.action_logger:
            decision = "APPROVED" if (completeness.status == "COMPLETE" and not issues) else "WARN"
            self.action_logger.log(
                action_type="BlueprintAudit",
                decision=decision,
                module="blueprint_auditor",
                status="Success",
                reason="Full audit",
                context=report.to_dict(),
            )

        if self.mission_log_sink:
            try:
                verdict = "halal" if (completeness.status == "COMPLETE" and not issues) else "shubha"
                score = 0.03 if verdict == "halal" else 0.5
                self.mission_log_sink(
                    {
                        "actor_id": "system:auditor",
                        "activity": "blueprint_full_audit",
                        "verdict": verdict,
                        "score": score,
                        "reasons": ["Audit completed"],
                        "tags": ["audit", "blueprint", "summary"],
                        "payload": report.to_dict(),
                    }
                )
            except Exception:
                pass

        return report
