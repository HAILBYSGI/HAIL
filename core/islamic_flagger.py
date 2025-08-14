# core/islamic_flagger.py
# HAIL — IslamicFlagger (Upgraded, backward compatible)
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

# Optional, best‑effort sinks (no hard dependency)
try:
    from core.action_logger import ActionLogger  # type: ignore
except Exception:  # pragma: no cover
    ActionLogger = None  # type: ignore

try:
    from core.deen_activity_monitor import (  # type: ignore
        DeenActivityMonitor, ActivityEvent, ActivityType
    )
except Exception:  # pragma: no cover
    DeenActivityMonitor = None  # type: ignore
    ActivityEvent = None  # type: ignore
    ActivityType = None  # type: ignore


@dataclass
class FlagItem:
    timestamp: str
    content: str
    context: str
    category: str           # e.g., "riba", "gambling", "music_ambiguous", ...
    severity: str           # low | medium | high | critical
    reason: str
    confidence: float       # 0..1 heuristic
    tags: List[str]
    risk: float             # 0..1 heuristic

    def to_dict(self) -> Dict:
        return asdict(self)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def _hash_key(content: str, context: str) -> str:
    h = hashlib.sha256()
    h.update((_norm(content) + "\x1f" + _norm(context)).encode("utf-8"))
    return h.hexdigest()[:16]


class IslamicFlagger:
    """
    Detects potentially haram or doubtful content with transparent, regex‑based rules.
    Backward‑compatible:
      - evaluate(content, context="") -> dict
      - get_all_flags() -> list
    New helpers:
      - flag_summary()
      - configure(exemptions=[...])
    """

    # Compile once: patterns grouped by category with default severity
    RULES: Dict[str, Dict] = {
        "riba_interest": {
            "severity": "high",
            "patterns": [r"\b(riba|interest|apr|usury)\b", "high apr", "compound interest", "سود", "بیاج"],
            "reason": "Financial usury/interest is prohibited (riba).",
        },
        "gambling": {
            "severity": "high",
            "patterns": [r"\b(gamble|betting|casino|roulette|lottery|jackpot)\b", "wager", "parlay", "پوکر"],
            "reason": "Gambling activities are prohibited.",
        },
        "nudity_porn": {
            "severity": "high",
            "patterns": [r"\b(porn|pornography|nudity|nude|nsfw)\b", "explicit content"],
            "reason": "Pornography/nudity is prohibited.",
        },
        "magic_divination": {
            "severity": "high",
            "patterns": [r"\b(astrology|horoscope|tarot|palm reading|black magic|sihr)\b"],
            "reason": "Sihr/divination/astrology is prohibited.",
        },
        "music_ambiguous": {
            "severity": "medium",
            "patterns": [r"\bmusic\b", "playlist", "dj", "bass boost", "gaana", "music sunao"],
            "reason": "Music may be doubtful; instrument‑free nasheed is generally exempt.",
        },
        "celebrity_culture": {
            "severity": "medium",
            "patterns": [r"\bcelebrity|idol|stan\b", "fan wars", "fandom"],
            "reason": "Celebrity/‘idol’ culture can lead to excess or shirk‑adjacent behavior.",
        },
        "non_mahram_interaction": {
            "severity": "medium",
            "patterns": ["flirt", r"\bdate\b", "dm a non mahram", "private dinner with colleague"],
            "reason": "Private/flirtatious non‑mahram interactions are discouraged/prohibited.",
        },
        "ibadah_inconsistency": {
            "severity": "medium",
            "patterns": ["pray later", "skip fasting", "salah can wait", "skip jummah"],
            "reason": "Ibadah delay/avoidance conflicts with obligations.",
        },
        "shirk_adjacent": {
            "severity": "high",
            "patterns": ["shaytan", "devil", "worship other than allah"],
            "reason": "Shirk‑adjacent mention; requires caution and context.",
        },
    }

    # Exemptions that can soften/ignore some categories
    DEFAULT_EXEMPTIONS = [
        "nasheed no instruments", "vocals only nasheed",
        "quran recitation", "tafseer", "tafsir", "education", "educational", "research only",
        "therapy", "ruqyah"
    ]

    def __init__(self, *, exemptions: Optional[List[str]] = None, mission_log_sink: Optional[callable] = None):
        self.flagged_items: List[Dict] = []  # legacy storage (list of dicts)
        self._dedupe: Dict[str, str] = {}    # key -> ts
        self._exempt = set((exemptions or self.DEFAULT_EXEMPTIONS))
        self._action_logger = ActionLogger() if ActionLogger else None
        self._mission_log_sink = mission_log_sink
        self._monitor = DeenActivityMonitor() if DeenActivityMonitor else None

        # precompile regexes
        self._compiled: Dict[str, List[re.Pattern]] = {
            cat: [re.compile(pat, re.I) if (pat.startswith(r"\b") or any(x in pat for x in "[]()|?+*"))
                  else re.compile(re.escape(pat), re.I)]
            for cat, spec in self.RULES.items()
            for pat in spec["patterns"]
        }
        # group compiled back by category
        self._compiled_by_cat: Dict[str, List[re.Pattern]] = {}
        for cat, spec in self.RULES.items():
            pats = []
            for pat in spec["patterns"]:
                if pat.startswith(r"\b") or any(x in pat for x in "[]()|?+*"):
                    pats.append(re.compile(pat, re.I))
                else:
                    pats.append(re.compile(re.escape(pat), re.I))
            self._compiled_by_cat[cat] = pats

    # ---------------- Backward‑compatible API ----------------

    def evaluate(self, content, context: str = ""):
        """
        Returns a dict:
          { flagged: bool, entry?: {...}, message?: str }
        (Backward compatible with original.)
        """
        text = _norm(content)
        ctx = _norm(context)
        key = _hash_key(text, ctx)

        # Dedupe identical content+context in a short session
        if key in self._dedupe:
            return {"flagged": True, "entry": {"deduped": True, "timestamp": self._dedupe[key]}}

        hits: List[FlagItem] = []
        for cat, pats in self._compiled_by_cat.items():
            if any(rx.search(text) for rx in pats):
                sev = self.RULES[cat]["severity"]
                reason = self.RULES[cat]["reason"]

                # Exemptions for some categories
                if cat in {"music_ambiguous", "celebrity_culture"} and any(x in text or x in ctx for x in self._exempt):
                    # soften or ignore depending on context
                    hits.append(FlagItem(
                        timestamp=_utcnow_iso(),
                        content=content,
                        context=context,
                        category=cat,
                        severity="low",
                        reason=f"{reason} – exemption/benefit recognized.",
                        confidence=0.55,
                        tags=["exemption", cat, "caution"],
                        risk=0.25
                    ))
                    continue

                # Normal case
                conf = 0.9 if sev in {"high", "critical"} else 0.7
                risk = 0.85 if sev in {"high", "critical"} else 0.5
                hits.append(FlagItem(
                    timestamp=_utcnow_iso(),
                    content=content,
                    context=context,
                    category=cat,
                    severity=sev,
                    reason=reason,
                    confidence=conf,
                    tags=[cat, "flag"],
                    risk=risk
                ))

        if hits:
            # combine highest‑severity hit into a single legacy entry,
            # but keep all hits in `details`
            top = sorted(hits, key=lambda x: ["low", "medium", "high", "critical"].index(x.severity))[-1]
            entry = {
                "content": content,
                "context": context,
                "flags": [h.to_dict() for h in hits],
                "top": top.to_dict(),
            }
            self.flagged_items.append(entry)
            self._dedupe[key] = top.timestamp

            # Sinks
            self._sink_action(top)
            self._sink_mission(top)
            self._emit_activity(top)

            return {"flagged": True, "entry": entry}

        return {"flagged": False, "message": "No concern detected"}

    def get_all_flags(self):
        # legacy accessor
        return self.flagged_items

    # ---------------- New helpers ----------------

    def flag_summary(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for row in self.flagged_items:
            for f in row.get("flags", []):
                cat = f.get("category", "unknown")
                counts[cat] = counts.get(cat, 0) + 1
        return counts

    def configure(self, *, exemptions: Optional[List[str]] = None):
        if exemptions is not None:
            self._exempt = set(exemptions)

    # ---------------- Sinks ----------------

    def _sink_action(self, top: FlagItem) -> None:
        if not self._action_logger:
            return
        try:
            self._action_logger.log(
                action_type="IslamicFlag",
                user_input=(_norm(top.content)[:200] or "content"),
                system_decision=top.severity.upper(),
                module="islamic_flagger",
                reason=f"{top.category}: {top.reason}",
                status="Flagged",
            )
        except Exception:
            pass

    def _sink_mission(self, top: FlagItem) -> None:
        if not callable(self._mission_log_sink):
            return
        try:
            verdict = "haram" if top.severity in {"high", "critical"} else "shubha"
            self._mission_log_sink({
                "actor_id": "system:flagger",
                "activity": "content_screen",
                "verdict": verdict,
                "score": top.risk,
                "reasons": [top.category, top.reason],
                "tags": ["flag", top.category, top.severity],
                "payload": top.to_dict(),
            })
        except Exception:
            pass

    def _emit_activity(self, top: FlagItem) -> None:
        if not (self._monitor and ActivityEvent and ActivityType):
            return
        try:
            self._monitor.emit(ActivityEvent.new(
                actor_id="system:flagger",
                activity=ActivityType.SYSTEM_EVENT,
                payload={"title": f"flag:{top.category}", "text": _norm(top.content)[:300]},
                tags=["flagger", top.severity, top.category],
            ))
        except Exception:
            pass


# ---------------- Minimal self-test ----------------
if __name__ == "__main__":
    f = IslamicFlagger()
    tests = [
        ("Play music for study session", "education"),
        ("Open a high APR credit card", ""),
        ("Try online roulette casino", ""),
        ("We can pray later after the party", ""),
        ("Reading horoscope daily", ""),
        ("Vocals only nasheed (no instruments) playlist", ""),
    ]
    for content, ctx in tests:
        print(json.dumps(f.evaluate(content, ctx), indent=2))
    print("Summary:", f.flag_summary())
