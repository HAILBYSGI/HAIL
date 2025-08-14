# core/quranic_violation_detector.py
# Part of HAIL – Deen Consistency & Safeguards

from __future__ import annotations
import re
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Dict, List, Iterable, Optional

_WORD_BOUND = r"\b{}(?:s)?\b"  # tolerate simple plurals

@dataclass
class ViolationRecord:
    ts: str
    text: str
    prohibited: List[str]
    caution: List[str]
    confidence: float  # 0..1 heuristic
    severity: str      # low|medium|high|critical

class QuranicViolationDetector:
    """
    Lightweight keyword-transparent detector.
    Public API (backward compatible):
      - scan_input(text) -> list[str]                       # matches in prohibited list (legacy)
      - detect_violation(text) -> {'violation': bool, ...}  # structured result
      - get_violation_log() -> list[dict]
    Extras:
      - add_keywords(kind, words)
      - reset_log()
      - export_log_json()
    """

    def __init__(self,
                 prohibited_keywords: Optional[List[str]] = None,
                 caution_keywords: Optional[List[str]] = None):
        self.prohibited_keywords: List[str] = prohibited_keywords or [
            "interest", "riba", "usury",
            "gambling",
            "alcohol", "liquor", "intoxicant",
            "nudity", "porn", "pornography", "zina", "adultery", "fornication",
            "haram", "shirk",
            "slander", "backbiting", "deceit", "lie",
            "black magic", "sorcery", "witchcraft", "fortune telling",
            "oppression", "murder", "suicide",
            "blasphemy", "bribe"
        ]
        self.caution_keywords: List[str] = caution_keywords or [
            "music", "idle talk", "luxury", "speculation", "waste",
            "boast", "envy", "arrogance", "non-mahram", "celebrity"
        ]
        self._log: List[ViolationRecord] = []

    # ---------- Backward-compat scan (prohibited only) ----------
    def scan_input(self, user_input: str) -> List[str]:
        t = self._normalize(user_input)
        return sorted(set(self._find_matches(t, self.prohibited_keywords)))

    # ---------- Main check ----------
    def detect_violation(self, user_input: str) -> Dict[str, object]:
        t = self._normalize(user_input)

        hits_prohibited = sorted(set(self._find_matches(t, self.prohibited_keywords)))
        hits_caution    = sorted(set(self._find_matches(t, self.caution_keywords)))

        # Heuristic scoring & severity
        score = 0.0
        severity = "low"
        if hits_prohibited:
            score = min(1.0, 0.75 + 0.05 * len(hits_prohibited))  # heavy weight
            severity = "critical" if len(hits_prohibited) >= 2 else "high"
        elif hits_caution:
            score = min(0.7, 0.35 + 0.05 * len(hits_caution))
            severity = "medium" if len(hits_caution) >= 2 else "low"

        violation = bool(hits_prohibited)

        result = {
            "violation": violation,
            "reason": "Qur’an-based ethical filter triggered" if violation else "No Qur’anic violation detected",
            "matched_terms": hits_prohibited if violation else [],
            "caution_terms": hits_caution,
            "severity": severity,
            "confidence": round(score, 3),
            "text_checked": user_input
        }

        # Append to log if anything noteworthy
        if violation or hits_caution:
            rec = ViolationRecord(
                ts=datetime.now(timezone.utc).isoformat(),
                text=user_input,
                prohibited=hits_prohibited,
                caution=hits_caution,
                confidence=round(score, 3),
                severity=severity,
            )
            self._log.append(rec)

        return result

    def get_violation_log(self) -> List[Dict[str, object]]:
        return [asdict(r) for r in self._log]

    # ---------- Maintenance ----------
    def reset_log(self) -> None:
        self._log = []

    def export_log_json(self) -> str:
        return json.dumps(self.get_violation_log(), ensure_ascii=False, indent=2)

    def add_keywords(self, kind: str, words: Iterable[str]) -> None:
        bucket = self._bucket(kind)
        for w in words:
            w = (w or "").strip().lower()
            if w and w not in bucket:
                bucket.append(w)

    # ---------- Internals ----------
    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join((text or "").lower().split())

    def _find_matches(self, text: str, vocab: List[str]) -> List[str]:
        hits: List[str] = []
        for w in vocab:
            pattern = _WORD_BOUND.format(re.escape(w))
            if re.search(pattern, text):
                hits.append(w)
        return hits

    def _bucket(self, kind: str) -> List[str]:
        k = (kind or "").strip().lower()
        if k.startswith("prohib"):
            return self.prohibited_keywords
        if k.startswith("caut"):
            return self.caution_keywords
        raise ValueError("Unknown keyword kind. Use 'prohibited' or 'caution'.")


# ---------------- Example usage ----------------
if __name__ == "__main__":
    qvd = QuranicViolationDetector()
    print(qvd.detect_violation("This plan includes riba and gambling, maybe some music."))
    print(qvd.detect_violation("Schedule zakat reminders and family halaqa."))
    print(qvd.get_violation_log())
