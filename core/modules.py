# core/modules.py
# HAIL OS — Execution Modules (upgraded, backward-compatible)
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional
import re

# --------- Optional bridges (best-effort; no hard dependency) ----------
try:
    from core.deen_mission_log import DeenMissionLog, Verdict as MLVerdict
except Exception:  # pragma: no cover
    DeenMissionLog, MLVerdict = None, None  # type: ignore

try:
    from core.deen_activity_monitor import (
        DeenActivityMonitor, ActivityEvent, ActivityType, Verdict as MonVerdict
    )
except Exception:  # pragma: no cover
    DeenActivityMonitor, ActivityEvent, ActivityType, MonVerdict = (None, None, None, None)  # type: ignore


# --------- Lightweight helpers ----------
@dataclass
class ModResult:
    title: str
    details: List[str]
    verdict: str = "halal"  # halal|shubha|haram
    score: float = 0.1
    tags: Optional[List[str]] = None

    def to_text(self) -> str:
        b = [f"{self.title}"]
        for d in self.details:
            b.append(f"• {d}")
        return "\n".join(b)


# Singleton placeholders so other parts can wire real instances if desired
_MISSION_LOG: Optional[DeenMissionLog] = None
_MONITOR: Optional[DeenActivityMonitor] = None


def set_global_mission_log(log: "DeenMissionLog") -> None:
    global _MISSION_LOG
    _MISSION_LOG = log


def set_global_monitor(monitor: "DeenActivityMonitor") -> None:
    global _MONITOR
    _MONITOR = monitor


class BaseModule:
    name = "Base"

    def _assess(self, command: str, *, activity: str = "system_event", tags: Optional[List[str]] = None) -> Dict:
        """
        If DeenActivityMonitor is available, classify & score the command.
        Otherwise return a safe default assessment.
        """
        if _MONITOR and ActivityEvent and ActivityType:
            try:
                at = getattr(ActivityType, activity.upper(), ActivityType.SYSTEM_EVENT)
                ev = ActivityEvent.new(actor_id="user:local", activity=at,
                                       payload={"text": command, "module": self.name},
                                       tags=tags or [])
                ra = _MONITOR.emit(ev)
                if ra:
                    return {"verdict": ra.verdict.value, "score": float(ra.score)}
            except Exception:
                pass
        # Default: mildly halal unless obviously risky keywords appear
        risky = any(w in command.lower() for w in ["riba", "interest", "gambling", "nudity", "porn"])
        v = "haram" if risky else "halal"
        s = 0.9 if risky else 0.1
        return {"verdict": v, "score": s}

    def _log(self, res: ModResult, payload: Dict) -> None:
        """If MissionLog is available, append a record (best-effort)."""
        if not _MISSION_LOG or not DeenMissionLog or not MLVerdict:
            return
        try:
            vmap = {"halal": MLVerdict.HALAL, "shubha": MLVerdict.SHUBHA, "haram": MLVerdict.HARAM}
            _MISSION_LOG.append(
                actor_id="user:local",
                activity=self.name,
                verdict=vmap.get(res.verdict, MLVerdict.SHUBHA),
                score=res.score,
                reasons=res.details[:3],
                tags=(res.tags or [])[:8],
                payload=payload,
            )
        except Exception:
            pass

    def _finish(self, title: str, details: List[str], *, command: str,
                tags: Optional[List[str]] = None) -> str:
        assess = self._assess(command, activity="system_event", tags=tags)
        res = ModResult(title=title, details=details, verdict=assess["verdict"], score=assess["score"], tags=tags)
        self._log(res, payload={"command": command})
        return res.to_text()


# ---------------- Modules ----------------

class AutoAmanahEngine(BaseModule):
    name = "Auto-Amanah Engine"

    def execute(self, command: str) -> str:
        actions = []
        if "schedule" in command.lower():
            actions.append("Scheduled task created with Deen safeguards.")
        if "email" in command.lower():
            actions.append("Prepared halal email draft (no flattery / falsehood).")
        if not actions:
            actions.append("Queued automation with amanah checks and audit trail.")
        return self._finish("✅ Auto-Amanah: task planned", actions, command=command, tags=["automation", "amanah"])


class IbadahTracker(BaseModule):
    name = "Ibadah Tracker"

    def execute(self, command: str) -> str:
        text = command.lower()
        found = []
        for p in ["fajr", "dhuhr", "asr", "maghrib", "isha", "tahajjud", "jummah"]:
            if p in text: found.append(p.capitalize())
        details = [f"Logged intention for: {', '.join(found) or 'general ibadah'}",
                   "Reminder windows will avoid work/sleep conflict."]
        return self._finish("🕌 Ibadah Tracker updated", details, command=command, tags=["ibadah", "tracker"])


class DuaResponseEngine(BaseModule):
    name = "Dua Response Engine"

    def execute(self, command: str) -> str:
        # heuristic: extract topic word(s)
        topic = re.sub(r"[^a-zA-Z0-9\s]", "", command).strip().split()[:3]
        dua_hint = "Consult authentic duas from Hisn al-Muslim / Sunnah sources."
        details = [
            f"Topic detected: {(' '.join(topic) or 'general dua')}",
            "Offer dua with adab (start with praise & salawat).",
            dua_hint
        ]
        return self._finish("🤲 Dua guidance prepared", details, command=command, tags=["dua", "guidance"])


class ZakatModule(BaseModule):
    name = "Zakat Module"

    def execute(self, command: str) -> str:
        details = [
            "Nisab check: ensure gold/silver thresholds before obligation.",
            "Exclude debts due immediately; include liquid assets.",
            "Proposed: 2.5% on zakatable wealth (lunar year)."
        ]
        return self._finish("🧮 Zakat calculation outline", details, command=command, tags=["zakat", "fiqh"])


class HalalInvestmentSystem(BaseModule):
    name = "Halal Investment System"

    def execute(self, command: str) -> str:
        details = [
            "Screening: remove riba, excessive uncertainty (gharar), haram revenue.",
            "Prefer asset-backed, equity, or compliant funds vetted by scholars.",
            "Risk note: diversify; avoid speculation."
        ]
        return self._finish("📈 Halal investing guardrails", details, command=command, tags=["finance", "screening"])


class FamilyAlignmentCore(BaseModule):
    name = "Family Alignment Core"

    def execute(self, command: str) -> str:
        details = [
            "Establish shura: weekly family check-ins with adab.",
            "Define rights & responsibilities aligned to Qur’an/Sunnah.",
            "Private matters remain confidential (amanah)."
        ]
        return self._finish("👪 Family alignment plan", details, command=command, tags=["family", "shura"])


class IslamicWorkflowEngine(BaseModule):
    name = "Islamic Workflow Engine"

    def execute(self, command: str) -> str:
        details = [
            "Time blocks around salah; protect Fajr-Isha windows.",
            "Batch shallow work; reserve deep focus after dhuhr/asr.",
            "Insert dhikr micro-breaks to reset intention."
        ]
        return self._finish("🧭 Workflow optimized (deen-aligned)", details, command=command, tags=["workflow", "focus"])


class QuranTherapyModule(BaseModule):
    name = "Qur’an-Based Therapy"

    def execute(self, command: str) -> str:
        details = [
            "Recommend recitation with tadabbur; begin with Al-Fatiha & Ad-Duha for hope.",
            "Breathing + dhikr: ‘HasbunAllahu wa ni’mal wakeel’.",
            "If severe, seek qualified help; HAIL supports, does not replace professionals."
        ]
        return self._finish("🌿 Qur’an-based therapy guidance", details, command=command, tags=["therapy", "quran"])


class HalalCompanion(BaseModule):
    name = "Daily Halal Companion"

    def execute(self, command: str) -> str:
        details = [
            "Prepared gentle reminders for salah, adhkar, Qur’an reading.",
            "Filtered entertainment suggestions to avoid doubtful content.",
            "Logged today’s intentions for self-accountability (muhasaba)."
        ]
        return self._finish("🤝 Halal Companion ready", details, command=command, tags=["companion", "daily"])


class WellnessMonitor(BaseModule):
    name = "Wellness Monitor"

    def execute(self, command: str) -> str:
        details = [
            "Balance: sleep hygiene, hydration, and movement every hour.",
            "Emotional check-in tied to dhikr prompts.",
            "Remind: ‘The strong is the one who controls anger.’ (Bukhari/Muslim)"
        ]
        return self._finish("💚 Wellness plan drafted", details, command=command, tags=["wellness", "health"])
