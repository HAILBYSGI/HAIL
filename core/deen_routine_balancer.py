# core/deen_routine_balancer.py
# HAIL — DeenRoutineBalancer (Upgraded)
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime, time
from typing import Any, Dict, List, Optional, Union

from core.shariah_guard import ShariahGuard

try:
    from core.action_logger import ActionLogger
except Exception:  # pragma: no cover
    ActionLogger = None  # type: ignore


StrOrTime = Union[str, time]
StrOrTimeOrDT = Union[str, time, datetime]


# ---------- Data models ----------
@dataclass
class RoutineGap:
    activity: str
    recommended_time: str
    shariah_compliant: Dict[str, Any]
    note: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RoutineReport:
    status: str  # "evaluated"
    missing_activities: List[RoutineGap] = field(default_factory=list)
    recommendation: str = (
        "Establish a balanced routine per Qur’an & Sunnah. Prioritize ṣalāh on time, daily Qur’an, and consistent adhkār."
    )
    next_actions: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["missing_activities"] = [m.to_dict() for m in self.missing_activities]
        return d


class DeenRoutineBalancer:
    """
    Compares a user's day against a Sunnah-aligned baseline and suggests improvements.

    Inputs accepted for user_log values:
      - True/False (completed or not)
      - "HH:MM" strings (24h)
      - datetime objects
      - textual markers (e.g., "after Fajr") are treated as completed if present

    Notes:
      - You can inject a more precise prayer timetable externally if needed.
      - Shari’ah check is tolerant: uses check_routine_compliance() if available,
        otherwise falls back to validate_action().
    """

    DEFAULT_ROUTINE: Dict[str, str] = {
        "Fajr": "05:00",
        "Dhuhr": "13:00",
        "Asr": "16:30",
        "Maghrib": "18:45",
        "Isha": "20:00",
        "Qur'an Recitation": "after Fajr",
        "Dhikr": "after Salah",
        "Du'a": "after Isha",
        "Tawbah": "before sleep",
    }

    def __init__(
        self,
        *,
        shariah_guard: Optional[ShariahGuard] = None,
        action_logger: Optional["ActionLogger"] = None,
        mission_log_sink: Optional[callable] = None,  # lambda payload: mission_log.append(...)
        baseline: Optional[Dict[str, str]] = None,
    ) -> None:
        self.shariah_guard = shariah_guard or ShariahGuard()
        self.log = action_logger
        self.mission_log_sink = mission_log_sink
        self.required_activities = dict(baseline or self.DEFAULT_ROUTINE)

    # ---------- Public API ----------

    def analyze_routine(self, user_log: Dict[str, StrOrTimeOrDT]) -> Dict[str, Any]:
        """
        Compare the provided user_log against the ideal routine.
        user_log example:
            {
              "Fajr": "05:12",
              "Qur'an Recitation": False,
              "Dhikr": "after Asr",
              "Du'a": True,
              ...
            }
        """
        missing: List[RoutineGap] = []
        completed, not_found = 0, 0

        for activity, recommended_time in self.required_activities.items():
            value = user_log.get(activity)

            if self._is_completed(value):
                completed += 1
                continue

            not_found += 1
            check = self._check_shariah(activity)
            note = self._gap_note(activity, recommended_time, value)
            missing.append(
                RoutineGap(
                    activity=activity,
                    recommended_time=str(recommended_time),
                    shariah_compliant=check,
                    note=note,
                )
            )

        report = RoutineReport(
            status="evaluated",
            missing_activities=missing,
            next_actions=self._next_actions(missing),
            meta={
                "total_required": len(self.required_activities),
                "completed": completed,
                "missing": not_found,
            },
        )

        self._sinks(report)
        return report.to_dict()

    def suggest_optimal_routine(self) -> Dict[str, Any]:
        """
        Return the baseline Sunnah-aligned plan (for UI display).
        """
        return {
            "routine": dict(self.required_activities),
            "note": "Align your day around these anchors for barakah, productivity, and spiritual stability.",
        }

    # ---------- Internals ----------

    def _is_completed(self, val: Optional[StrOrTimeOrDT]) -> bool:
        if val is None:
            return False
        if isinstance(val, bool):
            return val
        if isinstance(val, datetime):
            return True
        if isinstance(val, time):
            return True
        s = str(val).strip().lower()
        if not s:
            return False
        # Any non-empty textual marker (e.g., "after Fajr") means user did something
        # You can tighten this later with exact rules.
        if any(w in s for w in ("after", "before", "at", "done", "✔", "✅")):
            return True
        # "HH:MM"
        return self._parse_hhmm(s) is not None

    def _parse_hhmm(self, s: str) -> Optional[time]:
        try:
            hh, mm = s.split(":")
            return time(int(hh), int(mm))
        except Exception:
            return None

    def _check_shariah(self, text: str) -> Dict[str, Any]:
        # Prefer dedicated routine compliance if present
        try:
            if hasattr(self.shariah_guard, "check_routine_compliance"):
                res = self.shariah_guard.check_routine_compliance(text)
                if isinstance(res, dict):
                    return res
        except Exception:
            pass
        # Fallback to generic validator
        try:
            res = self.shariah_guard.validate_action(text)
            if isinstance(res, dict):
                return res
        except Exception:
            pass
        return {"allowed": True, "reason": "No explicit violation detected"}

    def _gap_note(self, activity: string, recommended_time: str, value: Any) -> str:  # type: ignore[name-defined]
        # typing quirk for 'string' fix below
        return f"Missing '{activity}'. Suggested time: {recommended_time}. Logged value: {value if value is not None else '—'}."

    def _next_actions(self, gaps: List[RoutineGap]) -> List[str]:
        actions: List[str] = []
        names = {g.activity for g in gaps}

        def add(line: str) -> None:
            if line not in actions:
                actions.append(line)

        # Priority: prayers first
        for p in ("Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"):
            if p in names:
                add(f"Schedule alarm + wudhu buffer for {p}; pray on time today.")

        # Daily anchors
        if "Qur'an Recitation" in names:
            add("Commit to 1 page of Qur’an after Fajr; track completion in HAIL.")
        if "Dhikr" in names:
            add("Set 3× daily adhkār windows: after Fajr, after ‘Asr, after ‘Ishā’.")
        if "Du'a" in names:
            add("Make 3 intentional du‘ās after ‘Ishā (health, guidance, rizq).")
        if "Tawbah" in names:
            add("End your day with istighfār (Astaghfirullāh 100×) before sleep.")

        if not actions:
            actions = ["Your core routine looks good. Maintain consistency and increase sincerity (iḥsān)."]
        return actions

    # ---------- Sinks ----------

    def _sinks(self, report: RoutineReport) -> None:
        # Action Logger
        if self.log:
            try:
                self.log.log(
                    action_type="RoutineBalance",
                    decision="APPROVED",
                    module="deen_routine_balancer",
                    status="Success",
                    reason=f"missing={len(report.missing_activities)}",
                    context=report.meta,
                    meta={"next_actions_preview": report.next_actions[:3]},
                )
            except Exception:
                pass

        # Mission Log (optional)
        if self.mission_log_sink:
            try:
                verdict = "halal" if len(report.missing_activities) == 0 else "shubha"
                score = 0.06 if verdict == "halal" else min(0.45, 0.1 + 0.05 * len(report.missing_activities))
                self.mission_log_sink(
                    {
                        "actor_id": "user",
                        "activity": "routine_evaluation",
                        "verdict": verdict,
                        "score": score,
                        "reasons": [f"Missing activities: {len(report.missing_activities)}"],
                        "tags": ["routine", "daily"],
                        "payload": report.to_dict(),
                    }
                )
            except Exception:
                pass
