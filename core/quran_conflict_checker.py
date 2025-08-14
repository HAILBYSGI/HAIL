# core/quran_conflict_checker.py
# Part of HAIL – Deen Consistency & Safeguards

from __future__ import annotations
import re
from dataclasses import dataclass, asdict
from typing import Dict, List, Iterable, Optional

_WORD = r"[A-Za-z0-9_']+"

@dataclass
class PrincipleRule:
    principle: str                     # e.g., "Truthfulness"
    reference: str                     # e.g., "Surah Al-Baqarah 2:42"
    keywords: List[str]                # signals that indicate conflict
    severity: str = "high"             # low|medium|high|critical
    remedy: Optional[str] = None       # optional guidance for correction

    def score(self, text: str) -> float:
        """
        Simple ratio of matched keywords in [0,1].
        """
        if not self.keywords:
            return 0.0
        hits = 0
        for kw in self.keywords:
            # use word boundaries to avoid substring false positives
            if re.search(rf"\b{re.escape(kw.lower())}\b", text):
                hits += 1
        return hits / len(self.keywords)

class QuranConflictChecker:
    """
    Lightweight, rule-driven checker for conflicts against Qur'anic principles.
    Keyword-based for transparency; can be extended with NLP later.

    Public API:
      - check_conflict(text) -> dict (backwards compatible)
      - has_conflict(text) -> bool
      - check_batch(texts) -> list[dict]
      - add_rule(rule) / list_rules()
    """

    def __init__(self):
        self._rules: List[PrincipleRule] = [
            PrincipleRule(
                principle="Truthfulness",
                reference="Surah Al-Baqarah 2:42",
                keywords=["lie", "lying", "fabricate", "falsehood"],
                severity="high",
                remedy="Speak the truth or remain silent; retract and correct any false statement."
            ),
            PrincipleRule(
                principle="Justice",
                reference="Surah An-Nahl 16:90",
                keywords=["unjust", "oppress", "oppression", "injustice", "cheat"],
                severity="critical",
                remedy="Restore rights, avoid zulm, and decide with fairness even against oneself."
            ),
            PrincipleRule(
                principle="No Compulsion in Religion",
                reference="Surah Al-Baqarah 2:256",
                keywords=["force religion", "coerce faith", "compel belief"],
                severity="high",
                remedy="Invite with wisdom (hikmah) and good counsel; avoid coercion."
            ),
            PrincipleRule(
                principle="Respect for Parents",
                reference="Surah Al-Isra 17:23",
                keywords=["disobey parents", "insult parents", "abuse parents"],
                severity="high",
                remedy="Speak with gentleness and kindness; seek forgiveness and serve them."
            ),
        ]

    # --------- public API ---------
    def check_conflict(self, action_description: str) -> Dict[str, object]:
        """
        Backward-compatible single-text check.
        """
        result = self._evaluate_text(action_description)
        if result["conflicts"]:
            return {"status": "conflict_detected", "conflicts": result["conflicts"]}
        return {"status": "no_conflict", "message": "No Qur'anic conflict detected."}

    def has_conflict(self, text: str) -> bool:
        return bool(self._evaluate_text(text)["conflicts"])

    def check_batch(self, texts: Iterable[str]) -> List[Dict[str, object]]:
        return [self.check_conflict(t) for t in texts]

    def add_rule(self, principle: str, reference: str, keywords: Iterable[str],
                 severity: str = "medium", remedy: Optional[str] = None) -> None:
        kws = [k.strip().lower() for k in keywords if k and k.strip()]
        self._rules.append(PrincipleRule(principle=principle, reference=reference,
                                         keywords=kws, severity=severity, remedy=remedy))

    def list_rules(self) -> List[Dict[str, object]]:
        return [asdict(r) for r in self._rules]

    # --------- internals ---------
    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(text.lower().split())

    def _evaluate_text(self, text: str) -> Dict[str, object]:
        t = self._normalize(text or "")
        conflicts: List[Dict[str, object]] = []

        for rule in self._rules:
            s = rule.score(t)
            if s > 0.0:
                conflicts.append({
                    "violation": rule.principle,
                    "reference": rule.reference,
                    "severity": rule.severity,
                    "confidence": round(min(1.0, s), 3),
                    "remedy": rule.remedy,
                    "matched": [kw for kw in rule.keywords if re.search(rf"\b{re.escape(kw)}\b", t)]
                })

        # sort by severity then confidence
        ordering = {"critical": 3, "high": 2, "medium": 1, "low": 0}
        conflicts.sort(key=lambda c: (ordering.get(str(c["severity"]).lower(), 0), c["confidence"]), reverse=True)

        return {"conflicts": conflicts}
    

# Example usage
if __name__ == "__main__":
    qc = QuranConflictChecker()
    print(qc.check_conflict("We should lie to close the deal."))
    print(qc.check_conflict("Do not oppress workers; decide justly."))
    print(qc.check_conflict("Invite them but never force religion on anyone."))
    print(qc.check_conflict("I might have to disobey parents about a minor issue."))
