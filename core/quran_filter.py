# core/quran_filter.py
# Part of HAIL – Deen Consistency & Safeguards

from __future__ import annotations
import re
from typing import Dict, List, Iterable, Tuple

_WORD_BOUND = r"\b{}(?:s)?\b"  # plural-tolerant word boundary

class QuranFilter:
    """
    Lightweight text filter aligned with Qur’anic ethics.
    Public APIs:
      - is_halal(text) -> bool                      (backward compatible)
      - analyze_text(text) -> {'status', 'issues'}  (backward compatible)
      - check_text(text) -> structured verdict {'allowed','verdict','danger','caution','score','reasons'}
      - add_keywords(kind, words) / list_keywords()
    """

    def __init__(self):
        # High-risk (haram) indicators
        self.prohibited_keywords: List[str] = [
            "haram", "shirk", "riba", "usury", "nudity", "porn", "pornography",
            "gambling", "intoxicant", "alcohol", "liquor", "bribe", "slander",
            "backbite", "black magic", "sorcery", "witchcraft", "adultery", "fornication"
        ]
        # Medium-risk (shubha) indicators that warrant caution
        self.caution_keywords: List[str] = [
            "music", "celebrity", "idle talk", "speculation", "luxury", "non-mahram",
            "waste", "boast", "arrogance", "envy", "gossip"
        ]

        # Optional whitelists (helps reduce false positives)
        self.allow_keywords: List[str] = [
            "zakat", "charity", "sadaqah", "quran", "hadith", "dua",
            "salah", "dhikr", "halal", "education", "islamic"
        ]

    # ---------------- Backward-compatible methods ----------------
    def is_halal(self, text: str) -> bool:
        """Return True if no prohibited term is present (legacy behavior)."""
        t = self._normalize(text)
        return not self._find_matches(t, self.prohibited_keywords)

    def analyze_text(self, text: str) -> Dict[str, object]:
        """Legacy analyzer returning Halal/Restricted with flat issues list."""
        t = self._normalize(text)
        issues = sorted(set(self._find_matches(t, self.prohibited_keywords)))
        if not issues:
            return {"status": "Halal", "issues": []}
        return {"status": "Restricted", "issues": issues}

    # ---------------- New structured verdict ----------------
    def check_text(self, text: str) -> Dict[str, object]:
        """
        Returns a structured verdict with severity separation and a risk score.
        verdict: 'halal' | 'shubha' | 'haram'
        """
        t = self._normalize(text)

        # Hits
        danger = sorted(set(self._find_matches(t, self.prohibited_keywords)))
        caution = sorted(set(self._find_matches(t, self.caution_keywords)))
        allow = sorted(set(self._find_matches(t, self.allow_keywords)))

        # Heuristic scoring (0..1)
        score = 0.0
        if danger:
            score = min(1.0, 0.75 + 0.05 * len(danger))  # heavy weight
            verdict = "haram"
            reasons = [f"Matched prohibited: {', '.join(danger)}"]
        elif caution:
            score = min(0.7, 0.35 + 0.05 * len(caution))
            verdict = "shubha"
            reasons = [f"Matched caution: {', '.join(caution)}"]
        else:
            verdict = "halal"
            reasons = ["No red flags detected"]

        if allow:
            reasons.append(f"Positive signals: {', '.join(allow)}")

        return {
            "allowed": verdict == "halal",
            "verdict": verdict,           # halal | shubha | haram
            "score": round(score, 3),     # 0..1 risk heuristic
            "danger": danger,             # matched prohibited terms
            "caution": caution,           # matched caution terms
            "positives": allow,           # matched positive terms
            "reasons": reasons,
            "text_checked": text
        }

    # ---------------- Keyword maintenance ----------------
    def add_keywords(self, kind: str, words: Iterable[str]) -> None:
        """
        kind: 'prohibited' | 'caution' | 'allow'
        """
        bucket = self._bucket(kind)
        for w in words:
            w = (w or "").strip().lower()
            if w and w not in bucket:
                bucket.append(w)

    def list_keywords(self) -> Dict[str, List[str]]:
        return {
            "prohibited": list(self.prohibited_keywords),
            "caution": list(self.caution_keywords),
            "allow": list(self.allow_keywords),
        }

    # ---------------- Internals ----------------
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
        k = kind.strip().lower()
        if k.startswith("prohib"):
            return self.prohibited_keywords
        if k.startswith("caut"):
            return self.caution_keywords
        if k.startswith("allow"):
            return self.allow_keywords
        raise ValueError("Unknown keyword kind. Use 'prohibited' | 'caution' | 'allow'.")


# ---------------- Example usage ----------------
if __name__ == "__main__":
    qf = QuranFilter()
    sample = "This message involves music and hints of riba; but also mentions zakat and education."
    print(qf.analyze_text(sample))
    print(qf.check_text(sample))
    print("is_halal:", qf.is_halal(sample))
