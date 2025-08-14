# core/deen_guardian_trigger.py
# HAIL — DeenGuardianTrigger (Upgraded)
# -----------------------------------------------------------------------------
# Purpose
# - Guard every user action with Shari’ah-first checks
# - Trigger Qur’anic violation records + taqwa alerts when needed
# - Notify Founder on serious violations (debounced to avoid spam)
# - Return a structured, auditable decision object
# - Optional: bridge from DeenActivityMonitor events
# -----------------------------------------------------------------------------

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Any, Dict, List, Optional

from core.islamic_action_checker import IslamicActionChecker
from core.founder_alert import FounderAlert
from core.quranic_violation_detector import QuranicViolationDetector
from core.taqwa_alert_manager import TaqwaAlertManager

try:
    from core.action_logger import ActionLogger
except Exception:  # pragma: no cover
    ActionLogger = None  # type: ignore

# Optional import if you want to route monitor events directly
try:
    from core.deen_activity_monitor import ActivityEvent, Classification, RiskAssessment, Verdict as MonitorVerdict
except Exception:  # pragma: no cover
    ActivityEvent = Classification = RiskAssessment = MonitorVerdict = None  # type: ignore


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class GuardianDecision:
    status: str                    # "allowed" | "blocked" | "warn"
    message: str
    actor_id: Optional[str] = None
    action_text: Optional[str] = None
    reasons: List[str] = field(default_factory=list)
    taqwa_alerted: bool = False
    quran_flagged: bool = False
    severity: str = "info"         # "info"|"low"|"medium"|"high"|"critical"
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # keep response compact
        if not d["reasons"]:
            d.pop("reasons")
        if not d["meta"]:
            d.pop("meta")
        return d


class DeenGuardianTrigger:
    """
    Shari’ah-first action gate with alerting & logging.
    Safety features:
      - Accepts bool or dict responses from IslamicActionChecker
      - Debounces repeated Founder alerts for same action text
      - Mirrors results to ActionLogger / Mission Log (optional)
      - Bridge method for DeenActivityMonitor events
    """

    def __init__(
        self,
        *,
        action_checker: Optional[IslamicActionChecker] = None,
        quran_violation: Optional[QuranicViolationDetector] = None,
        taqwa_manager: Optional[TaqwaAlertManager] = None,
        alert: Optional[FounderAlert] = None,
        action_logger: Optional["ActionLogger"] = None,
        mission_log_sink: Optional[callable] = None,  # lambda payload: mission_log.append(...)
        alert_cooldown: timedelta = timedelta(seconds=20),
    ) -> None:
        self.action_checker = action_checker or IslamicActionChecker()
        self.quran_violation = quran_violation or QuranicViolationDetector()
        self.taqwa_manager = taqwa_manager or TaqwaAlertManager()
        self.alert = alert or FounderAlert()
        self.log = action_logger
        self.mission_log_sink = mission_log_sink

        self._lock = RLock()
        self._last_alert_at: Dict[str, datetime] = {}
        self._alert_cooldown = alert_cooldown

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate_user_action(
        self,
        action: str,
        *,
        actor_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        severity: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Guard a free-text user action/intent.
        Returns GuardianDecision as dict.
        """
        action_text = (action or "").strip()
        if not action_text:
            return GuardianDecision(
                status="warn",
                message="Empty action provided.",
                actor_id=actor_id,
                action_text=action_text,
                severity="low",
                reasons=["No action text"],
            ).to_dict()

        # 1) Shari’ah check — tolerate both legacy and new checker responses
        verdict, reasons, level = self._check_action(action_text)

        # 2) Take actions based on verdict
        if verdict == "haram":
            qflag = self._flag_quran(action_text, actor_id)
            talert = self._taqwa_alert(action_text, actor_id)
            self._notify_founder_once(f"⛔ Action flagged as **haram**: {action_text}", key=action_text)
            decision = GuardianDecision(
                status="blocked",
                message=f"⛔ Action flagged as haram and blocked.",
                actor_id=actor_id,
                action_text=action_text,
                reasons=reasons or ["Shari’ah violation detected"],
                taqwa_alerted=talert,
                quran_flagged=qflag,
                severity=level or "high",
                meta={"context": context or {}},
            )
        elif verdict == "shubha":
            talert = self._taqwa_alert(action_text, actor_id)
            decision = GuardianDecision(
                status="warn",
                message="⚠️ Action in doubtful (shubha) zone; proceed with caution or seek a halal alternative.",
                actor_id=actor_id,
                action_text=action_text,
                reasons=reasons or ["Doubtful area"],
                taqwa_alerted=talert,
                quran_flagged=False,
                severity=level or "medium",
                meta={"context": context or {}},
            )
        else:
            decision = GuardianDecision(
                status="allowed",
                message=f"✅ Action approved.",
                actor_id=actor_id,
                action_text=action_text,
                reasons=reasons or ["No violation detected"],
                taqwa_alerted=False,
                quran_flagged=False,
                severity=severity or "info",
                meta={"context": context or {}},
            )

        # 3) Sinks
        self._sinks(decision)

        return decision.to_dict()

    # Optional: bridge directly from DeenActivityMonitor callbacks
    def evaluate_monitor_event(
        self,
        ev: "ActivityEvent",
        c: "Classification",
        r: "RiskAssessment",
    ) -> Optional[Dict[str, Any]]:
        """
        If you subscribe this method to DeenActivityMonitor, it will
        auto-trigger guardian checks for suspicious events.
        Only acts when monitor verdict is shubha/haram.
        """
        if not (ActivityEvent and Classification and RiskAssessment and MonitorVerdict):
            return None  # monitor not available

        if c.verdict == MonitorVerdict.HALAL:
            return None

        text = ev.payload.get("title") or ev.payload.get("text") or ev.payload.get("url") or ev.activity.value
        ctx = {"monitor_score": r.score, "tags": list(ev.tags), "payload": ev.payload}
        # Map monitor verdict to a severity hint
        sev = "high" if c.verdict == MonitorVerdict.HARAM else "medium"
        return self.evaluate_user_action(text, actor_id=ev.actor_id, context=ctx, severity=sev)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _check_action(self, action_text: str) -> (str, List[str], str):
        """
        Normalize checker output.
        Returns: (verdict: 'halal'|'shubha'|'haram', reasons, severity)
        """
        try:
            res = self.action_checker.is_halal(action_text)
            # Legacy: bool -> map
            if isinstance(res, bool):
                return ("halal" if res else "haram", [], "high" if not res else "info")
            # Dict style
            if isinstance(res, dict):
                allowed = bool(res.get("allowed", True))
                if not allowed and res.get("level") == "haram":
                    return "haram", res.get("reasons", []), str(res.get("severity", "high"))
                if not allowed:
                    return "shubha", res.get("reasons", []), str(res.get("severity", "medium"))
                # allowed
                return "halal", res.get("reasons", []), str(res.get("severity", "info"))
        except Exception as e:
            # Fail safe to shubha
            return "shubha", [f"Checker error: {type(e).__name__}"], "medium"

        # Default conservative
        return "shubha", ["No clear result from checker"], "medium"

    def _flag_quran(self, action_text: str, actor_id: Optional[str]) -> bool:
        try:
            self.quran_violation.flag_violation(action_text)
            return True
        except Exception:
            return False

    def _taqwa_alert(self, action_text: str, actor_id: Optional[str]) -> bool:
        try:
            self.taqwa_manager.trigger_taqwa_alert(action_text)
            return True
        except Exception:
            return False

    def _notify_founder_once(self, body: str, *, key: str) -> None:
        """
        Debounce founder notifications for identical actions within cooldown.
        """
        now = datetime.now(timezone.utc)
        with self._lock:
            last = self._last_alert_at.get(key)
            if last and (now - last) < self._alert_cooldown:
                return
            self._last_alert_at[key] = now
        try:
            self.alert.send("🚨 DEEN GUARDIAN ALERT", body)
        except Exception:
            pass

    def _sinks(self, decision: GuardianDecision) -> None:
        # Action Logger
        if self.log:
            try:
                self.log.log(
                    action_type="Guardian",
                    decision=("APPROVED" if decision.status == "allowed" else "DENIED" if decision.status == "blocked" else "WARN"),
                    module="deen_guardian_trigger",
                    status="Success",
                    user_input=decision.action_text,
                    actor_id=decision.actor_id,
                    reason=(decision.reasons[0] if decision.reasons else decision.message)[:300],
                    context={"severity": decision.severity, "taqwa_alerted": decision.taqwa_alerted, "quran_flagged": decision.quran_flagged},
                    meta=decision.meta,
                )
            except Exception:
                pass

        # Mission Log (optional)
        if self.mission_log_sink:
            try:
                verdict_map = {"allowed": "halal", "warn": "shubha", "blocked": "haram"}
                score_map = {"allowed": 0.05, "warn": 0.45, "blocked": 0.85}
                self.mission_log_sink(
                    {
                        "actor_id": decision.actor_id or "user",
                        "activity": "guardian_check",
                        "verdict": verdict_map.get(decision.status, "shubha"),
                        "score": score_map.get(decision.status, 0.4),
                        "reasons": decision.reasons[:3] if decision.reasons else [decision.message],
                        "tags": ["guardian", decision.severity],
                        "payload": decision.to_dict(),
                    }
                )
            except Exception:
                pass


# ---------------- Example quick test ----------------
if __name__ == "__main__":
    g = DeenGuardianTrigger(action_logger=ActionLogger(also_print=True) if ActionLogger else None)
    print(g.evaluate_user_action("Watch interest-based loan tutorials", actor_id="husnain_ali"))
    print(g.evaluate_user_action("Give charity to local masjid", actor_id="husnain_ali"))
