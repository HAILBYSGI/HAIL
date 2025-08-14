# core/dynamic_phase_router.py
# HAIL — DynamicPhaseRouter (Upgraded)
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional, Tuple

from core.query_matcher import QueryMatcher
from core.phase_mapper import PhaseMapper
from core.system_indexer import SystemIndexer

try:
    from core.action_logger import ActionLogger
except Exception:  # pragma: no cover
    ActionLogger = None  # type: ignore


@dataclass
class RouteCandidate:
    system: str
    phase: str
    score: float
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["score"] = round(self.score, 3)
        return d


@dataclass
class RouteResult:
    status: str                         # "high-confidence" | "medium-confidence" | "low-confidence" | "error"
    confidence: float
    phase: Optional[str]
    target_system: Optional[str] = None
    candidates: List[RouteCandidate] = field(default_factory=list)
    message: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["candidates"] = [c.to_dict() for c in self.candidates]
        out["confidence"] = round(self.confidence, 3)
        return out


class DynamicPhaseRouter:
    """
    Router that maps free‑form queries to indexed systems/phases.
    - Uses QueryMatcher to get best system match (+ score)
    - Uses PhaseMapper to infer phase from intent/keywords
    - Consults SystemIndexer for availability / canonical names
    - Produces ranked candidates and a final route decision
    """

    def __init__(
        self,
        *,
        hi_threshold: float = 0.80,
        med_threshold: float = 0.55,
        action_logger: Optional["ActionLogger"] = None,
        mission_log_sink: Optional[callable] = None,  # lambda payload: mission_log.append(...)
    ):
        self.query_matcher = QueryMatcher()
        self.phase_mapper = PhaseMapper()
        self.system_indexer = SystemIndexer()
        self.hi = float(hi_threshold)
        self.med = float(med_threshold)
        self.log = action_logger
        self.mission_log_sink = mission_log_sink

    # --------------- Public API ---------------

    def route(self, user_query: str) -> Dict[str, Any]:
        """
        Returns a structured routing decision for the query.
        """
        try:
            q = (user_query or "").strip()
            if not q:
                return self._emit(self._error("Empty query"))

            # 1) Primary match
            score, system = self.query_matcher.match(q)  # expected (float, "system_name")
            score = float(score or 0.0)
            system = str(system or "").strip() or None

            # 2) Phase inference
            phase = self.phase_mapper.map_to_phase(q)  # e.g., "Phase 3 – Command Flow & Ethics"

            # 3) Candidate expansion (best-effort): ask indexer for close systems
            #    If QueryMatcher exposes a top_k method in your codebase, swap this in.
            candidates: List[RouteCandidate] = []
            try:
                # naive expansion: validate the matched system against index, add neighbors
                catalog = self.system_indexer.index_systems({})  # your indexer may ignore {}
                # catalog could be dict or list depending on your implementation
                if isinstance(catalog, dict):
                    names = list(catalog.keys())
                elif isinstance(catalog, list):
                    names = [str(x) for x in catalog]
                else:
                    names = []

                # simple heuristic candidate: the matched system (if any)
                if system:
                    candidates.append(RouteCandidate(system=system, phase=str(phase), score=score, reason="primary"))
                # optionally include a couple of similarly named systems
                near = [n for n in names if system and n != system and n.lower().startswith(system[:4].lower())]
                for n in near[:3]:
                    candidates.append(RouteCandidate(system=n, phase=str(phase), score=max(0.5, score * 0.8), reason="neighbor"))

            except Exception:
                # ignore candidate expansion errors; keep primary only
                if system:
                    candidates.append(RouteCandidate(system=system, phase=str(phase), score=score, reason="primary"))

            # 4) Decision
            if score >= self.hi and system:
                res = RouteResult(
                    status="high-confidence",
                    confidence=score,
                    phase=str(phase),
                    target_system=system,
                    candidates=sorted(candidates, key=lambda c: c.score, reverse=True),
                    meta={"thresholds": {"high": self.hi, "medium": self.med}},
                )
            elif score >= self.med and system:
                res = RouteResult(
                    status="medium-confidence",
                    confidence=score,
                    phase=str(phase),
                    target_system=system,
                    candidates=sorted(candidates, key=lambda c: c.score, reverse=True),
                    message="Proceed with caution or ask for brief clarification.",
                    meta={"thresholds": {"high": self.hi, "medium": self.med}},
                )
            else:
                res = RouteResult(
                    status="low-confidence",
                    confidence=score,
                    phase=str(phase),
                    target_system=None,
                    candidates=sorted(candidates, key=lambda c: c.score, reverse=True),
                    message="Query requires Founder input or fallback logic.",
                    meta={"thresholds": {"high": self.hi, "medium": self.med}},
                )

            return self._emit(res)

        except Exception as e:
            return self._emit(self._error(repr(e)))

    # --------------- Internals / sinks ---------------

    def _emit(self, res: RouteResult | Dict[str, Any]) -> Dict[str, Any]:
        if isinstance(res, RouteResult):
            payload = res.to_dict()
        else:
            payload = res

        # ActionLogger
        if self.log:
            try:
                self.log.log(
                    action_type="Routing",
                    user_input=payload.get("meta", {}).get("query_preview", "") or "",
                    system_decision=payload.get("status", ""),
                    module="dynamic_phase_router",
                    reason=f"target={payload.get('target_system')} phase={payload.get('phase')} conf={payload.get('confidence')}",
                    status="Success",
                )
            except Exception:
                pass

        # Mission Log
        if self.mission_log_sink:
            try:
                verdict = "halal"
                score = 0.08 if payload.get("status") in ("high-confidence", "medium-confidence") else 0.25
                self.mission_log_sink(
                    {
                        "actor_id": "user",
                        "activity": "routing_decision",
                        "verdict": verdict,
                        "score": score,
                        "reasons": [f"route:{payload.get('status')}"],
                        "tags": ["routing", payload.get("phase") or "unknown"],
                        "payload": payload,
                    }
                )
            except Exception:
                pass

        return payload

    def _error(self, msg: str) -> RouteResult:
        return RouteResult(status="error", confidence=0.0, phase=None, message=msg, meta={})
