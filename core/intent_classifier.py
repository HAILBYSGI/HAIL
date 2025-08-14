# core/intent_classifier.py
# HAIL — IntentClassifier (Upgraded, backward compatible)
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional


@dataclass
class IntentRule:
    target: str                 # module/system name
    keywords: List[str]         # simple substrings or regexes
    weight: float = 1.0         # contribution to score


class IntentClassifier:
    """
    Keyword + regex + weights classifier.
    Backward compatible:
      - classify(text) -> str   (returns module name or 'General Inquiry')
    New:
      - classify_pro(text) -> dict {intent, confidence, target}
      - classify_emotion(text) -> one of {'anger','sadness','stress','envy','fear','lazy','calm','unknown'}
    """

    def __init__(self) -> None:
        # Canonical intent -> target module mapping
        self._routes: Dict[str, IntentRule] = {
            # Automation / Tasks
            "automation": IntentRule(
                target="AutoAmanahEngine",
                keywords=[
                    r"\bautomate\b", r"\bautomation\b", r"\bschedule\b", r"\bworkflow\b",
                    "auto-amanah", "integrate", "trigger", "cron", "zapier",
                    # Urdu hints
                    "automate karo", "schedule bana", "kaam automate"
                ],
                weight=1.0
            ),
            # Ibadah
            "ibadah": IntentRule(
                target="IbadahTracker",
                keywords=[
                    r"\b(fajr|dhuhr|asr|maghrib|isha)\b", r"\b(pray|salah|namaz)\b",
                    "wudu", "ramadan", "fast", "taraweeh", "tahajjud",
                    "ibadah", "ziker", "dhikr", "tasbeeh",
                    "namaz yaad", "ibadat"
                ],
                weight=1.2
            ),
            # Dua
            "dua": IntentRule(
                target="DuaResponseEngine",
                keywords=[
                    r"\bdua\b", r"\bdu[\u2019']a\b", "supplication", "make a prayer",
                    "dua batao", "dua chahiye", "istikhara"
                ],
                weight=1.1
            ),
            # Zakat / Charity
            "zakat": IntentRule(
                target="ZakatModule",
                keywords=[
                    r"\bzakat\b", "charity", "donation", "sadaqah", "fitrah",
                    "calculate zakat", "zakat hisab", "zakaat"
                ],
                weight=1.15
            ),
            # Investment / Business
            "investment": IntentRule(
                target="HalalInvestmentSystem",
                keywords=[
                    "halal investment", "stocks halal", "sukuk", "mudarabah", "musharakah",
                    "business plan", "scale business", "ethical finance",
                    "investment karo", "business halal"
                ],
                weight=1.1
            ),
            # Family
            "family": IntentRule(
                target="FamilyAlignmentCore",
                keywords=[
                    "marriage", "nikah", "parenting", "spouse", "in-laws",
                    "family issue", "rishta", "talaq"
                ],
                weight=1.0
            ),
            # Focus / Work
            "workflow": IntentRule(
                target="IslamicWorkflowEngine",
                keywords=[
                    "focus", "plan my day", "task list", "pomodoro", "deep work",
                    "work schedule", "timebox", "workflow", "productivity"
                ],
                weight=0.95
            ),
            # Therapy / Healing
            "therapy": IntentRule(
                target="QuranTherapyModule",
                keywords=[
                    "therapy", "healing", "counsel", "counseling", "anxiety", "depression",
                    "sad", "grief", "hopeless", "hearts find rest", "ruqyah"
                ],
                weight=1.0
            ),
            # Wellness / Health
            "wellness": IntentRule(
                target="WellnessMonitor",
                keywords=[
                    "health", "sleep", "diet", "exercise", "wellness", "stress",
                    "pain", "headache", "tired", "fatigue"
                ],
                weight=0.9
            ),
            # Daily Assistant
            "daily": IntentRule(
                target="HalalCompanion",
                keywords=[
                    "help", "assistant", "remind", "note", "translate", "summarize",
                    "shopping list", "what should i do", "guide me", "today plan"
                ],
                weight=0.8
            ),
        }

        # Emotion hints (used by several Deen-* modules)
        self._emotions: List[Tuple[str, List[str]]] = [
            ("anger", ["angry", "furious", "mad", "rage", "ghussa", "irritated"]),
            ("sadness", ["sad", "depressed", "down", "hopeless", "rona", "cry"]),
            ("stress", ["stressed", "overwhelmed", "pressure", "tension", "anxious"]),
            ("envy", ["envy", "hasad", "jealous", "jealousy"]),
            ("fear", ["fear", "afraid", "scared", "dar", "khauf"]),
            ("lazy", ["lazy", "procrastinate", "怠け", "susti", "sluggish"]),
            ("calm", ["calm", "peaceful", "sakoon", "content"]),
        ]

        # Precompile regexes for speed
        self._compiled = {
            name: [re.compile(pat, re.I) if pat.startswith(r"\b") or "[" in pat or "(" in pat else re.compile(re.escape(pat), re.I)
                   for pat in rule.keywords]
            for name, rule in self._routes.items()
        }

    # ---------------- Public: Backward-compatible ----------------

    def classify(self, user_input: str) -> str:
        """
        Returns the target module name (legacy behavior).
        Falls back to 'General Inquiry'.
        """
        pro = self.classify_pro(user_input)
        return pro.get("target") or "General Inquiry"

    # ---------------- Public: New ----------------

    def classify_pro(self, user_input: str) -> Dict[str, object]:
        """
        Returns a structured result:
          { "intent": <canonical-intent>, "confidence": 0..1, "target": <module or None> }
        """
        text = self._normalize(user_input)
        if not text:
            return {"intent": "unknown", "confidence": 0.0, "target": None}

        best_intent: Optional[str] = None
        best_score: float = 0.0

        for intent, rule in self._routes.items():
            score = 0.0
            patterns = self._compiled[intent]
            for rx in patterns:
                # heavier reward for whole-word matches
                if rx.search(text):
                    score += 1.0
            score *= rule.weight

            if score > best_score:
                best_score, best_intent = score, intent

        # Map score to confidence (simple logistic-ish squashing)
        confidence = min(1.0, best_score / 4.0) if best_score > 0 else 0.0
        target = self._routes[best_intent].target if best_intent else None

        return {"intent": best_intent or "unknown", "confidence": round(confidence, 3), "target": target}

    def classify_emotion(self, text: str) -> str:
        """
        Very light signal for emotions used by Deen modules.
        """
        s = self._normalize(text)
        if not s:
            return "unknown"
        best = ("unknown", 0)
        for label, keys in self._emotions:
            hits = sum(1 for k in keys if re.search(rf"\b{re.escape(k)}\b", s, re.I))
            if hits > best[1]:
                best = (label, hits)
        return best[0]

    # ---------------- Internals ----------------

    @staticmethod
    def _normalize(s: str) -> str:
        if not s:
            return ""
        # strip diacritics and punctuation, lower-case
        s = unicodedata.normalize("NFKD", s)
        s = "".join(ch for ch in s if not unicodedata.combining(ch))
        s = s.lower()
        # keep word boundaries, remove extra punctuation except basic separators
        s = re.sub(r"[^\w\s'-]", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s


# ---------------- Minimal self-test ----------------
if __name__ == "__main__":
    clf = IntentClassifier()
    tests = [
        "Automate my bills and schedule reminders",
        "Missed Fajr — help me with Ibadah routine",
        "Best dua for anxiety?",
        "Calculate Zakat for gold",
        "Halal investment options in stocks",
        "Marriage counseling",
        "Focus plan for deep work",
        "Feeling depressed and stressed",
        "Daily assistant: make a shopping list",
        "Translate this to Urdu",
    ]
    for t in tests:
        print(t, "->", clf.classify_pro(t))
    print("Emotion:", clf.classify_emotion("I feel angry and irritated today"))
