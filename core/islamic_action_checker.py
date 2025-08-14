# core/islamic_action_checker.py
# HAIL — IslamicActionChecker (Upgraded, backward compatible)
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional


@dataclass
class CheckResult:
    status: str              # "APPROVED" | "WARNING" | "DENIED"
    reason: str
    tags: List[str]
    confidence: float        # 0..1 (heuristic)
    category: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)


class IslamicActionChecker:
    """
    Lightweight halal/shubha/haram gate based on transparent keyword/regex rules.
    Backward compatible:
      - evaluate_action(text) -> dict {status, reason}
    New helpers:
      - is_halal(text) -> bool
      - score(text) -> float (0..1 risk, 0 best)
    """

    def __init__(self) -> None:
        # ---------- Prohibited (DENIED) ----------
        self._deny: Dict[str, List[str]] = {
            "riba_interest": [
                r"\b(riba|interest|apr|usury)\b", "compound interest", "pay interest",
                "سود", "بیاج"
            ],
            "gambling": [
                r"\b(gamble|betting|casino|roulette|lottery|jackpot)\b", "parlay", "wager", "پوکر"
            ],
            "nudity_porn": [
                r"\b(porn|pornography|nsfw|nudity|nude)\b", "explicit content"
            ],
            "magic_divination": [
                r"\b(astrology|horoscope|tarot|palm reading|black magic|sihr)\b"
            ],
            "slander_falsehood": [
                r"\b(defame|slander|libel|false testimony|fake evidence)\b"
            ],
            "surveillance": [
                r"\bspy(on)?\b", "surveillance without consent", "stalkerware", "keylogger"
            ],
            "intoxicants": [
                r"\b(alcohol|wine|beer|liquor)\b", "sell alcohol", "brew alcohol"
            ],
        }

        # ---------- Doubtful (WARNING) ----------
        self._flag: Dict[str, List[str]] = {
            "music_ambiguous": [
                r"\bmusic\b", "song", "playlist", "dj", "bass boost",
                # Urdu/alt
                "gaana", "music sunao"
            ],
            "celebrity_culture": [
                r"\bcelebrity|idol|stan\b", "fan wars", "fandom"
            ],
            "speculation_risk": [
                r"\b(leverage|options trading|forex scalping|pump and dump)\b", "meme coin"
            ],
            "luxury_excess": [
                r"\bluxury|extravagant|lavish\b", "gold-plated", "show off"
            ],
            "non_mahram_mix": [
                r"\bdate\b", "flirt", "dm a non[- ]?mahram", "private dinner with colleague"
            ],
        }

        # ---------- Exemptions / clarifiers ----------
        # If these appear together with a WARNING token, we soften the verdict.
        self._exempt_ok: List[str] = [
            "nasheed no instruments", "vocals only nasheed", "quran recitation",
            "study purpose", "educational", "research only", "therapy", "ruqyah"
        ]

    # ---------------- Public API ----------------

    def evaluate_action(self, action_text: str) -> Dict:
        """
        Backward‑compatible: returns dict with at least {status, reason}.
        Upgraded result also contains tags, confidence, category.
        """
        res = self._check(action_text)
        # Preserve old shape keys while returning rich info
        return {
            "status": res.status,
            "reason": res.reason,
            "tags": res.tags,
            "confidence": round(res.confidence, 3),
            "category": res.category,
        }

    def is_halal(self, action_text: str) -> bool:
        return self._check(action_text).status == "APPROVED"

    def score(self, action_text: str) -> float:
        """
        Risk score 0..1 (0 best). WARNING ~0.4-0.6, DENIED ~0.8-1.0
        """
        res = self._check(action_text)
        if res.status == "APPROVED":
            return 0.05
        if res.status == "WARNING":
            return min(0.6, 0.35 + 0.1 * len(res.tags))
        return min(1.0, 0.8 + 0.05 * len(res.tags))

    # ---------------- Internals ----------------

    @staticmethod
    def _norm(s: str) -> str:
        return re.sub(r"\s+", " ", (s or "").lower()).strip()

    def _match_any(self, text: str, patterns: List[str]) -> bool:
        for pat in patterns:
            if pat.startswith(r"\b") or any(ch in pat for ch in "[]()|?+*"):
                if re.search(pat, text, flags=re.I):
                    return True
            elif pat in text:
                return True
        return False

    def _has_exemption(self, text: str) -> bool:
        return any(tok in text for tok in self._exempt_ok)

    def _check(self, action_text: str) -> CheckResult:
        t = self._norm(action_text)

        # DENIED rules first (hard stop)
        for category, patterns in self._deny.items():
            if self._match_any(t, patterns):
                return CheckResult(
                    status="DENIED",
                    reason=f"Prohibited content detected ({category.replace('_',' ')}).",
                    tags=["haram", category],
                    confidence=0.9,
                    category=category,
                )

        # WARNING rules
        warning_hits: List[str] = []
        hit_category: Optional[str] = None
        for category, patterns in self._flag.items():
            if self._match_any(t, patterns):
                warning_hits.append(category)
                hit_category = hit_category or category

        if warning_hits:
            # Exemptions can soften WARNING to APPROVED with caution
            if self._has_exemption(t):
                return CheckResult(
                    status="APPROVED",
                    reason=f"Ambiguous area flagged ({', '.join(warning_hits)}), but exemption/benefit recognized.",
                    tags=["caution", *warning_hits, "exemption"],
                    confidence=0.55,
                    category=hit_category,
                )
            return CheckResult(
                status="WARNING",
                reason=f"Doubtful/ambiguous area detected ({', '.join(warning_hits)}). Proceed with caution.",
                tags=["shubha", *warning_hits],
                confidence=0.7,
                category=hit_category,
            )

        # APPROVED default
        return CheckResult(
            status="APPROVED",
            reason="No conflicts detected against current rule set.",
            tags=["halal"],
            confidence=0.6,
            category=None,
        )


# ---------------- Minimal self-test ----------------
if __name__ == "__main__":
    c = IslamicActionChecker()
    tests = [
        "Schedule Fajr prayer reminder",
        "Set up halal investment portfolio",
        "Play music during party",
        "Arrange vocals only nasheed (no instruments)",
        "Open a high APR credit card (interest)",
        "Try online roulette casino",
        "Spy on colleague laptop without consent",
        "Plan a lavish luxury birthday",
    ]
    for t in tests:
        print(t, "->", c.evaluate_action(t))
