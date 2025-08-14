# core/shariah_guard.py
# Filters HAIL actions based on Qur'an and Sunnah compliance
# Compatible with modules that call:
#   - is_halal(), is_halal_action()
#   - validate_action(text)
#   - check_content(text)
#   - verify_emotion(emotion)
#   - check_routine_compliance(activity)
#   - enforce_max_filter_level(), reset_filter_level()
#   - set_taqwa_level(level)

from __future__ import annotations
from typing import Dict, List, Optional

from core.quran_filter import QuranFilter
from core.quranic_violation_detector import QuranicViolationDetector
from core.islamic_action_checker import IslamicActionChecker
from core.override_filter import OverrideFilter

# Secure logger is optional; guard import for environments without cryptography
try:
    from core.secure_logger import SecureLogger  # type: ignore
except Exception:  # pragma: no cover
    SecureLogger = None  # type: ignore


class ShariahGuard:
    """
    Central halal/haram decision layer.

    Pipeline (short-circuit on hard violations):
      1) OverrideFilter: block explicit attempts to bypass deen
      2) QuranicViolationDetector: prohibited/caution terms with severity & confidence
      3) IslamicActionChecker: domain rules (prohibited/doubtful/approved)
      4) QuranFilter: generic prohibited keywords
      5) Taqwa sensitivity: tighten/relax borderline acceptance
    """

    # Emotions that require correction (used by DeenEmotionGuard)
    _FORBIDDEN_EMOTIONS = {"envy", "arrogance", "anger"}

    def __init__(self,
                 taqwa_level: float = 0.6,  # 0..1 (higher = stricter)
                 enable_logging: bool = True):
        self.taqwa_level = float(max(0.0, min(1.0, taqwa_level)))
        self.quran_filter = QuranFilter()
        self.qvd = QuranicViolationDetector()
        self.checker = IslamicActionChecker()
        self.override_filter = OverrideFilter()
        self.logger = SecureLogger() if (enable_logging and SecureLogger) else None

        # Local explicit prohibited tokens (can be extended)
        self.prohibited_keywords: List[str] = [
            "interest", "riba", "gambling", "nudity", "forbidden", "alcohol", "music-haram"
        ]

        # Operational filter level (raised in emergency mode)
        self._max_guard = False

    # ---------------- Public API (legacy-compatible) ----------------

    def is_halal_action(self, user_input: str) -> bool:
        """Legacy name kept for compatibility."""
        return self.is_halal(user_input)

    def is_halal(self, user_input: str) -> bool:
        """Boolean convenience check."""
        return self.validate_action(user_input)["allowed"]

    def validate_action(self, user_input: str) -> Dict[str, object]:
        """
        Main decision method. Returns:
        {
          'allowed': bool,
          'verdict': 'halal'|'shubha'|'haram',
          'reasons': [..],
          'confidence': float
        }
        """
        text = (user_input or "").strip()

        # 1) Hard override attempts
        if not self.override_filter.is_command_allowed(text):
            res = {
                "allowed": False,
                "verdict": "haram",
                "reasons": [self.override_filter.explain_restriction(text)["reason"]],
                "confidence": 0.95
            }
            self._log("ShariahGuard", "override_block", "BLOCKED", {"text": text, "stage": "override"})
            return res

        reasons: List[str] = []
        worst_verdict = "halal"
        confidence = 0.0

        # 2) Qur’anic violation detector (prohibited & caution)
        v = self.qvd.detect_violation(text)
        if v.get("violation"):
            worst_verdict = "haram"
            confidence = max(confidence, float(v.get("confidence", 0.85)))
            reasons.append(f"QVD: prohibited={v.get('matched_terms')}, severity={v.get('severity')}")
        elif v.get("caution_terms"):
            worst_verdict = self._worse(worst_verdict, "shubha")
            confidence = max(confidence, float(v.get("confidence", 0.5)))
            reasons.append(f"QVD caution={v.get('caution_terms')}")

        # 3) IslamicActionChecker rules
        chk = self.checker.evaluate_action(text)
        status = chk.get("status", "APPROVED")
        if status == "DENIED":
            worst_verdict = "haram"
            confidence = max(confidence, 0.9)
            reasons.append(f"IAC: {chk.get('reason')}")
        elif status == "WARNING":
            worst_verdict = self._worse(worst_verdict, "shubha")
            confidence = max(confidence, 0.55)
            reasons.append(f"IAC caution: {chk.get('reason')}")

        # 4) Generic keyword filter (QuranFilter)
        qf = self.quran_filter.analyze_text(text)
        if qf.get("status") == "Restricted":
            worst_verdict = "haram"
            confidence = max(confidence, 0.8)
            reasons.append(f"QF restricted: {qf.get('issues')}")

        # 5) Local prohibited list
        low = text.lower()
        for w in self.prohibited_keywords:
            if w in low:
                worst_verdict = "haram"
                confidence = max(confidence, 0.8)
                reasons.append(f"Local prohibited keyword: {w}")

        # 6) Taqwa sensitivity and emergency mode
        if self._max_guard and worst_verdict != "haram":
            # In emergency, downgrade anything borderline to shubha/blocked
            worst_verdict = "shubha"
            confidence = max(confidence, 0.7)
            reasons.append("Emergency mode tightening")

        # Thresholding based on taqwa level
        allowed = (worst_verdict == "halal")
        if worst_verdict == "shubha":
            # Strictness threshold: block doubtful if taqwa high or emergency
            if self.taqwa_level >= 0.6 or self._max_guard:
                allowed = False
                reasons.append(f"Blocked due to taqwa={self.taqwa_level:.2f}")
            else:
                allowed = True
                reasons.append(f"Allowed with caution (taqwa={self.taqwa_level:.2f})")

        verdict = worst_verdict
        result = {
            "allowed": allowed,
            "verdict": verdict,
            "reasons": reasons or ["No issues detected."],
            "confidence": round(float(confidence or (0.35 if verdict == "halal" else 0.7)), 3)
        }

        self._log("ShariahGuard", "validate_action", "OK" if allowed else "BLOCKED",
                  {"text": text, "verdict": verdict, "reasons": reasons})
        return result

    def check_content(self, text: str) -> Dict[str, object]:
        """
        Used by DeenDistractionFilter. Returns a compact disposition record.
        """
        res = self.validate_action(text)
        return {
            "allowed": res["allowed"],
            "category": res["verdict"],     # 'halal' | 'shubha' | 'haram'
            "confidence": res["confidence"],
            "notes": res["reasons"]
        }

    def verify_emotion(self, emotion: str) -> bool:
        """
        True = emotion acceptable; False = needs correction.
        """
        return (emotion or "").strip().lower() not in self._FORBIDDEN_EMOTIONS

    def check_routine_compliance(self, activity: str) -> bool:
        """
        Very light rule: any prayer/Qur’an/dhikr is compliant; anything with explicit haram is not.
        """
        t = (activity or "").lower()
        if any(k in t for k in ("fajr", "dhuhr", "asr", "maghrib", "isha", "qur'an", "quran", "dhikr", "dua", "du'a")):
            return True
        return self.is_halal(t)

    # ---------------- Ops Controls ----------------

    def enforce_max_filter_level(self) -> None:
        """Used by DeenEmergencyMode to tighten all checks."""
        self._max_guard = True
        self._log("ShariahGuard", "enforce_max_filter_level", "ON", {"taqwa": self.taqwa_level})

    def reset_filter_level(self) -> None:
        """Restore normal operation."""
        self._max_guard = False
        self._log("ShariahGuard", "reset_filter_level", "OFF", {"taqwa": self.taqwa_level})

    def set_taqwa_level(self, level: float) -> None:
        """0..1; higher means stricter on doubtful content."""
        self.taqwa_level = float(max(0.0, min(1.0, level)))
        self._log("ShariahGuard", "set_taqwa_level", "OK", {"taqwa": self.taqwa_level})

    # ---------------- Internals ----------------

    @staticmethod
    def _worse(a: str, b: str) -> str:
        order = {"halal": 0, "shubha": 1, "haram": 2}
        return a if order[a] >= order[b] else b

    def _log(self, module: str, action: str, status: str, metadata: Optional[Dict] = None) -> None:
        if self.logger:
            try:
                self.logger.log(module=module, action=action, status=status, metadata=metadata or {})
            except Exception:
                # Never break guard flow due to logging
                pass


# ---------------- Quick self-test ----------------
if __name__ == "__main__":
    sg = ShariahGuard(taqwa_level=0.6)
    print(sg.validate_action("Schedule zakat reminders for family halaqa"))
    print(sg.validate_action("Open a high-interest savings account"))
    print(sg.check_content("Play music at the party"))
    print("verify_emotion('envy'):", sg.verify_emotion("envy"))
    sg.enforce_max_filter_level()
    print(sg.validate_action("Borderline: celebrity news and idle talk"))
    sg.reset_filter_level()
    sg.set_taqwa_level(0.3)
    print(sg.validate_action("Borderline: celebrity news and idle talk"))
