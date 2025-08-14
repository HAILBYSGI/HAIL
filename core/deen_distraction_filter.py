# core/deen_distraction_filter.py
# HAIL — DeenDistractionFilter (Upgraded)

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, Iterable, List, Optional, Tuple
from datetime import datetime, timezone

from core.shariah_guard import ShariahGuard

try:
    from core.action_logger import ActionLogger
except Exception:  # pragma: no cover
    ActionLogger = None  # type: ignore


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DistractionHit:
    activity_text: str
    matched: List[str]
    categories: List[str]
    weight: float
    halal_status: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "activity": self.activity_text,
            "matched": list(self.matched),
            "categories": list(self.categories),
            "weight": float(self.weight),
            "halal_status": self.halal_status,
        }


@dataclass
class FilterReport:
    status: str                       # "filtered"
    total_activities: int
    hits: List[DistractionHit] = field(default_factory=list)
    total_score: float = 0.0
    advice: str = (
        "Reduce distractions that pull you away from Qur’an, Ṣalāh, and Islamic growth. "
        "Replace with dhikr, Qur’an recitation, or beneficial Islamic learning."
    )
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "total_activities": self.total_activities,
            "total_score": round(self.total_score, 3),
            "flagged_distractions": [h.to_dict() for h in self.hits],
            "advice": self.advice,
            "notes": list(self.notes),
        }


class DeenDistractionFilter:
    """
    Scans user activities and flags distractions (entertainment overuse, idle scrolling, etc.)
    Pipeline:
      1) Normalize inputs (strings or dicts with 'text'/'title')
      2) Match against distraction dictionary (keywords -> category, weight)
      3) Shari'ah check for the text (validate_action / check_content)
      4) Aggregate score and return structured report
      5) Optional sinks: ActionLogger + Mission Log
    """

    # keyword -> (category, weight)
    _DICT: Dict[str, Tuple[str, float]] = {
        # entertainment / passive
        "netflix": ("entertainment", 0.9),
        "tiktok": ("entertainment", 0.9),
        "reels": ("entertainment", 0.85),
        "gaming": ("gaming", 0.8),
        "pubg": ("gaming", 0.85),
        "call of duty": ("gaming", 0.85),
        "browsing": ("idle", 0.6),
        "scroll": ("idle", 0.65),
        "doomscroll": ("idle", 0.8),
        "idle talk": ("idle", 0.6),
        "social media": ("social", 0.75),
        "instagram": ("social", 0.75),
        "facebook": ("social", 0.7),
        "twitter": ("social", 0.7),
        "x.com": ("social", 0.7),
        "youtube shorts": ("entertainment", 0.85),
        "music": ("music", 0.9),           # general; haram music blocked by guard
        "spotify": ("music", 0.75),
        "overuse of phone": ("overuse", 0.7),
        "phone": ("overuse", 0.4),
    }

    def __init__(
        self,
        *,
        shariah_guard: Optional[ShariahGuard] = None,
        action_logger: Optional["ActionLogger"] = None,
        mission_log_sink: Optional[callable] = None,   # lambda payload: mission_log.append(...)
        extra_keywords: Optional[Dict[str, Tuple[str, float]]] = None,
    ) -> None:
        self.shariah_guard = shariah_guard or ShariahGuard()
        self.log = action_logger
        self.mission_log_sink = mission_log_sink
        self.dict = dict(self._DICT)
        if extra_keywords:
            self.dict.update({k.lower(): v for k, v in extra_keywords.items()})

    # --------------- Public API ---------------

    def detect_distractions(self, activity_log: Iterable[Any]) -> Dict[str, Any]:
        """
        Accepts:
          - ['Watched Netflix', 'Scrolling TikTok', ...]
          - [{'text':'Watched Netflix'}, {'title':'Gaming late night'}]
        Returns FilterReport as dict.
        """
        texts: List[str] = [self._extract_text(a) for a in activity_log if self._extract_text(a)]
        hits: List[DistractionHit] = []
        total_score = 0.0

        for raw in texts:
            t = raw.lower()
            matched: List[str] = []
            cats: List[str] = []
            w_sum = 0.0

            for kw, (cat, w) in self.dict.items():
                if kw in t:
                    matched.append(kw)
                    if cat not in cats:
                        cats.append(cat)
                    w_sum += w

            if matched:
                halal_status = self._check_halal(raw)
                hit = DistractionHit(
                    activity_text=raw,
                    matched=sorted(matched),
                    categories=sorted(cats),
                    weight=round(min(1.0, w_sum), 3),
                    halal_status=halal_status,
                )
                hits.append(hit)
                total_score += hit.weight

        rep = FilterReport(
            status="filtered",
            total_activities=len(texts),
            hits=hits,
            total_score=round(min(len(texts), total_score), 3),
            notes=["score ~ sum of weights per hit (capped at 1.0 each)"],
        )

        # sinks
        self._sinks(rep)
        return rep.to_dict()

    def recommend_alternatives(self) -> Dict[str, Any]:
        return {
            "alternatives": [
                "Listen to authentic Islamic lectures",
                "Read Qur’an with tafsīr (even 1 page)",
                "Join a 20-minute online halaqah/class",
                "Do dhikr/tasbīḥ (e.g., 33× each)",
                "Volunteer or help a family member",
                "Short walk while reciting adhkār",
            ],
            "note": "Balance any leisure with your obligations. HAIL can auto-remind or rate-limit distracting apps if enabled.",
        }

    # A small motivational nudge based on score
    def coach(self, total_score: float) -> str:
        if total_score >= 4:
            return "Quite a heavy distraction day. Try a 30-minute digital detox, then 2 rak‘ah + 5 minutes of Qur’an."
        if total_score >= 2:
            return "Some distractions crept in. Schedule 10 minutes of dhikr now and one page of Qur’an before sleep."
        if total_score > 0:
            return "Light distractions noticed. Keep it steady—make a brief du‘ā and refocus on a small task."
        return "Great focus today. Increase gratitude—say Alḥamdulillāh and keep your routine strong."

    # --------------- Internals ---------------

    def _extract_text(self, item: Any) -> Optional[str]:
        if item is None:
            return None
        if isinstance(item, str):
            return item.strip()
        if isinstance(item, dict):
            for k in ("text", "title", "activity", "name", "description"):
                if k in item and isinstance(item[k], str) and item[k].strip():
                    return item[k].strip()
        return None

    def _check_halal(self, text: str) -> Dict[str, Any]:
        """
        Be compatible with different ShariahGuard APIs:
          - validate_action(text) -> dict
          - check_content(text)   -> dict
        """
        try:
            res = self.shariah_guard.validate_action(text)  # preferred in newer modules
            if isinstance(res, dict):
                return res
        except Exception:
            pass
        try:
            res = self.shariah_guard.check_content(text)  # fallback for older API
            if isinstance(res, dict):
                return res
        except Exception:
            pass
        return {"allowed": True, "reason": "No explicit violation detected"}

    def _sinks(self, rep: FilterReport) -> None:
        # Action logger
        if self.log:
            try:
                decision = "WARN" if rep.total_score > 0 else "APPROVED"
                self.log.log(
                    action_type="DistractionFilter",
                    decision=decision,
                    module="deen_distraction_filter",
                    status="Success",
                    reason=f"score={rep.total_score}",
                    context={
                        "total_activities": rep.total_activities,
                        "hits": [h.to_dict() for h in rep.hits[:5]],  # trim preview
                    },
                )
            except Exception:
                pass

        # Mission Log (optional)
        if self.mission_log_sink:
            try:
                verdict = "shubha" if rep.total_score > 0 else "halal"
                score = min(0.9, 0.2 + 0.15 * rep.total_score) if rep.total_score > 0 else 0.04
                self.mission_log_sink(
                    {
                        "actor_id": "system:distraction_filter",
                        "activity": "distraction_scan",
                        "verdict": verdict,
                        "score": float(score),
                        "reasons": [f"Total distraction score={rep.total_score}"],
                        "tags": ["focus", "discipline"],
                        "payload": rep.to_dict(),
                    }
                )
            except Exception:
                pass


# -------- Example quick test --------
if __name__ == "__main__":
    # from core.action_logger import ActionLogger
    logger = ActionLogger(also_print=True) if ActionLogger else None
    f = DeenDistractionFilter(action_logger=logger)
    test = [
        "Watched Netflix documentary",
        {"text": "Scrolling TikTok for an hour"},
        {"title": "Gaming late night — PUBG"},
        "Phone overuse before Fajr",
        "Qur’an recitation for 15 minutes",
    ]
    rep = f.detect_distractions(test)
    print(rep)
    print("Coach:", f.coach(rep["total_score"]))
