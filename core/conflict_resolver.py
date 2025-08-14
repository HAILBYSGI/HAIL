# core/conflict_resolver.py
# Part of HAIL Phase 3 – AI Ethics, Command & Security Logic (Upgraded)

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional, Any, Tuple

try:
    from core.action_logger import ActionLogger
except Exception:  # pragma: no cover
    ActionLogger = None  # type: ignore


@dataclass
class Signal:
    """Normalized module decision signal."""
    status: str                      # "ALLOW" | "DENY" | "WARN" | "ABSTAIN"
    reason: str = ""
    reasons: List[str] = field(default_factory=list)
    severity: str = "info"           # "info" | "low" | "medium" | "high" | "critical"
    verified: bool = False           # e.g., founder override verification
    evidence: Dict[str, Any] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_obj(obj: Any) -> "Signal":
        if isinstance(obj, Signal):
            return obj
        if isinstance(obj, dict):
            return Signal(
                status=str(obj.get("status", "ABSTAIN")).upper(),
                reason=obj.get("reason", ""),
                reasons=list(obj.get("reasons", [])),
                severity=str(obj.get("severity", "info")).lower(),
                verified=bool(obj.get("verified", False)),
                evidence=dict(obj.get("evidence", {})),
                meta=dict(obj.get("meta", {})),
            )
        # default
        return Signal(status="ABSTAIN", reason="Unrecognized signal type")


@dataclass
class Resolution:
    final_status: str                # "APPROVED" | "DENIED" | "WARN" | "NO_DECISION"
    resolved_by: str                 # which module determined outcome
    reason: str
    reasons: List[str] = field(default_factory=list)
    trail: Dict[str, Any] = field(default_factory=dict)  # all inputs + normalized
    severity_max: str = "info"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ConflictResolver:
    """
    Priority-based conflict resolution with Shari'ah-first invariant.

    Priority order (highest -> lowest):
        1) shariah_guard
        2) founder_protocol
        3) intent_classifier
        4) action_handler

    Rules:
      - Any DENY from shariah_guard => immediate DENIED (cannot be overridden).
      - founder_protocol may ALLOW only if shariah_guard did not DENY, and if verified=True.
      - WARN signals propagate as final WARN only if no explicit ALLOW/DENY resolved above.
      - ABSTAIN contributes no decision.
    """

    def __init__(
        self,
        *,
        priority_order: Optional[List[str]] = None,
        weights: Optional[Dict[str, float]] = None,
        logger: Optional["ActionLogger"] = None,
        mission_log_sink: Optional[callable] = None,
    ) -> None:
        self.priority_order = priority_order or [
            "shariah_guard",
            "founder_protocol",
            "intent_classifier",
            "action_handler",
        ]
        self.weights = {k: float(v) for k, v in (weights or {}).items()}
        self.log = logger
        self.mission_log_sink = mission_log_sink

    # ---------------- core API ----------------

    def resolve(self, signals: Dict[str, Any]) -> Dict[str, Any]:
        """
        signals: dict[module_name] = Signal | dict-like
        Example:
          {
            'shariah_guard': {'status': 'DENY', 'reason': 'Against Qur’an'},
            'founder_protocol': {'status': 'ALLOW', 'verified': True},
            'intent_classifier': {'status': 'ALLOW'}
          }
        """
        # Normalize all signals
        norm: Dict[str, Signal] = {m: Signal.from_obj(s) for m, s in (signals or {}).items()}

        # 1) Shari'ah-first hard gate
        sg = norm.get("shariah_guard")
        if sg and sg.status == "DENY":
            res = self._make_resolution(
                final="DENIED",
                by="shariah_guard",
                primary_reason=sg.reason or "Shari'ah violation",
                reasons=sg.reasons,
                trail=norm,
                severity_max=self._max_severity(norm),
            )
            self._write_logs(res)
            return res.to_dict()

        # 2) Founder protocol can ALLOW only if verified and no Shari'ah DENY
        fp = norm.get("founder_protocol")
        if fp and fp.status == "DENY":
            res = self._make_resolution(
                final="DENIED",
                by="founder_protocol",
                primary_reason=fp.reason or "Founder protocol denial",
                reasons=fp.reasons,
                trail=norm,
                severity_max=self._max_severity(norm),
            )
            self._write_logs(res)
            return res.to_dict()

        if fp and fp.status == "ALLOW":
            if fp.verified:
                # allowed, but still consider WARNs downstream for visibility
                res = self._maybe_warn_else_approve("founder_protocol", fp, norm)
                self._write_logs(res)
                return res.to_dict()
            else:
                # unverified founder allow -> treat as WARN at best
                # continue to evaluate others
                pass

        # 3) Walk priority for any explicit DENY or ALLOW
        for module in self.priority_order:
            sig = norm.get(module)
            if not sig:
                continue
            if sig.status == "DENY":
                res = self._make_resolution(
                    final="DENIED",
                    by=module,
                    primary_reason=sig.reason or f"{module} denial",
                    reasons=sig.reasons,
                    trail=norm,
                    severity_max=self._max_severity(norm),
                )
                self._write_logs(res)
                return res.to_dict()
            if sig.status == "ALLOW":
                # Approved — but if other modules WARN with high/critical, surface WARN
                res = self._maybe_warn_else_approve(module, sig, norm)
                self._write_logs(res)
                return res.to_dict()

        # 4) No explicit allow/deny: consider WARN dominance
        warn_by, warn_sig = self._highest_warn(norm)
        if warn_sig:
            res = self._make_resolution(
                final="WARN",
                by=warn_by,
                primary_reason=warn_sig.reason or "Caution advised",
                reasons=warn_sig.reasons,
                trail=norm,
                severity_max=self._max_severity(norm),
            )
            self._write_logs(res)
            return res.to_dict()

        # 5) Nothing decisive → default approve (no critical conflict)
        res = self._make_resolution(
            final="APPROVED",
            by="default_flow",
            primary_reason="No critical conflict found.",
            reasons=[],
            trail=norm,
            severity_max=self._max_severity(norm),
        )
        self._write_logs(res)
        return res.to_dict()

    # ---------------- helpers ----------------

    def _maybe_warn_else_approve(self, by: str, sig: Signal, norm: Dict[str, Signal]) -> Resolution:
        # If any WARN with severity high/critical exists, surface WARN
        _, ws = self._highest_warn(norm)
        if ws and ws.severity in ("high", "critical"):
            return self._make_resolution(
                final="WARN",
                by=by,
                primary_reason=ws.reason or "High-severity warning present",
                reasons=(sig.reasons + ws.reasons),
                trail=norm,
                severity_max=self._max_severity(norm),
            )
        return self._make_resolution(
            final="APPROVED",
            by=by,
            primary_reason=sig.reason or f"{by} approval",
            reasons=sig.reasons,
            trail=norm,
            severity_max=self._max_severity(norm),
        )

    def _highest_warn(self, norm: Dict[str, Signal]) -> Tuple[str, Optional[Signal]]:
        # choose WARN with highest severity; tie-break by priority and weight
        candidates: List[Tuple[str, Signal]] = [(m, s) for m, s in norm.items() if s.status == "WARN"]
        if not candidates:
            return "", None

        def score(item: Tuple[str, Signal]) -> Tuple[int, float]:
            m, s = item
            sev_rank = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}.get(s.severity, 0)
            prio_rank = len(self.priority_order) - (self.priority_order.index(m) if m in self.priority_order else -1)
            weight = self.weights.get(m, 1.0)
            # higher tuple sorts first
            return (sev_rank, prio_rank * weight)

        candidates.sort(key=score, reverse=True)
        return candidates[0]

    def _max_severity(self, norm: Dict[str, Signal]) -> str:
        order = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
        max_s = max((order.get(s.severity, 0) for s in norm.values()), default=0)
        for k, v in order.items():
            if v == max_s:
                return k
        return "info"

    def _make_resolution(self, *, final: str, by: str, primary_reason: str, reasons: List[str], trail: Dict[str, Signal], severity_max: str) -> Resolution:
        merged_reasons = [r for r in ([primary_reason] + list(reasons)) if r]
        # materialize trail as plain dict
        tdict = {m: asdict(s) for m, s in trail.items()}
        return Resolution(
            final_status=final,
            resolved_by=by,
            reason=primary_reason,
            reasons=merged_reasons,
            trail=tdict,
            severity_max=severity_max,
        )

    def _write_logs(self, res: Resolution) -> None:
        # ActionLogger sink
        if self.log:
            decision = "APPROVED" if res.final_status == "APPROVED" else ("WARN" if res.final_status == "WARN" else "DENIED")
            self.log.log(
                action_type="ConflictResolution",
                decision=decision,
                module="conflict_resolver",
                status="Success",
                reason=res.reason,
                context={"final_status": res.final_status, "resolved_by": res.resolved_by, "severity_max": res.severity_max},
                meta={"reasons": res.reasons},
            )

        # MissionLog sink (optional)
        if self.mission_log_sink:
            try:
                verdict = "halal" if res.final_status == "APPROVED" else ("shubha" if res.final_status == "WARN" else "haram")
                score = {"APPROVED": 0.02, "WARN": 0.45, "DENIED": 0.85}.get(res.final_status, 0.5)
                self.mission_log_sink(
                    {
                        "actor_id": "system:conflict_resolver",
                        "activity": "conflict_resolution",
                        "verdict": verdict,
                        "score": score,
                        "reasons": res.reasons[:3],
                        "tags": ["conflict", "routing"],
                        "payload": res.to_dict(),
                    }
                )
            except Exception:
                pass


# Example usage
if __name__ == "__main__":
    resolver = ConflictResolver()
    test_signals = {
        'shariah_guard': {'status': 'ALLOW', 'reason': 'No violation'},
        'intent_classifier': {'status': 'ALLOW', 'reason': 'Detected user command'},
        'founder_protocol': {'status': 'DENY', 'reason': 'Founder has not approved override'},
    }
    print(resolver.resolve(test_signals))
