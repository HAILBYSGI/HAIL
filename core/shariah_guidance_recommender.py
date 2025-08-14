# core/shariah_guidance_recommender.py
# Provides concise, source-backed guidance for common fiqh/akhlaq issues.
# Compatible with simple key lookups and free-text detection.

from __future__ import annotations
from typing import Dict, List, Optional


class ShariahGuidanceRecommender:
    def __init__(self):
        # Minimal, high-signal dataset (expandable)
        self.guidance_data: Dict[str, Dict[str, str]] = {
            "lying": {
                "ruling": "Haram",
                "hadith": "“Truthfulness leads to righteousness, and righteousness leads to Paradise… lying leads to the Fire.” — Bukhari & Muslim (summary)",
                "quran": "Surah Al-Baqarah 2:42"
            },
            "interest": {
                "ruling": "Haram",
                "hadith": "“The Prophet ﷺ cursed the one who takes riba, the one who gives it, the one who records it, and its witnesses.” — Muslim",
                "quran": "Surah Al-Baqarah 2:275"
            },
            "salah_missed": {
                "ruling": "Severe Warning",
                "hadith": "“The difference between us and them is the prayer; whoever abandons it has disbelieved.” — Tirmidhi (disputed grading; severe warning agreed)",
                "quran": "Surah Maryam 19:59"
            },
            "backbiting": {
                "ruling": "Haram",
                "hadith": "“Backbiting is to mention about your brother what he dislikes.” — Muslim",
                "quran": "Surah Al-Hujurat 49:12"
            },
            "alcohol": {
                "ruling": "Haram",
                "hadith": "“Every intoxicant is khamr and every khamr is haram.” — Muslim",
                "quran": "Surah Al-Ma’idah 5:90–91"
            },
            "gambling": {
                "ruling": "Haram",
                "hadith": "Gambling (maysir) is explicitly forbidden with alcohol in the same verses.",
                "quran": "Surah Al-Ma’idah 5:90–91"
            },
            "modesty_breach": {
                "ruling": "Haram / Avoid",
                "hadith": "“Modesty is part of faith.” — Bukhari & Muslim",
                "quran": "Surah An-Nur 24:30–31"
            },
            "parents_disrespect": {
                "ruling": "Major Sin",
                "hadith": "“Shall I not inform you of the greatest of major sins? … Disrespect to parents.” — Bukhari & Muslim",
                "quran": "Surah Al-Isra 17:23"
            },
        }

        # Simple free-text keyword mapping for auto-detection
        self._keyword_map: Dict[str, List[str]] = {
            "lying": ["lie", "lying", "fake", "fabricate", "false claim"],
            "interest": ["interest", "riba", "usury", "apr", "loan interest"],
            "salah_missed": ["missed salah", "missed prayer", "qaza", "qadha", "skipped fajr", "missed fajr"],
            "backbiting": ["backbite", "backbiting", "gheebah", "gheebat", "talk behind"],
            "alcohol": ["alcohol", "wine", "beer", "intoxicant", "drink party"],
            "gambling": ["gamble", "bet", "casino", "maysir", "lottery"],
            "modesty_breach": ["immodest", "nudity", "exposed", "revealing pics", "non-mahram flirting"],
            "parents_disrespect": ["argue parents", "rude to father", "rude to mother", "talk back parents"],
        }

    # ---------------- Public API ----------------

    def recommend(self, issue_key: str) -> Dict[str, str]:
        key = self._normalize_key(issue_key)
        data = self.guidance_data.get(key)
        if data:
            return {
                "status": "guidance_found",
                "issue": key,
                "ruling": data["ruling"],
                "hadith": data["hadith"],
                "quran_reference": data["quran"],
            }
        return {
            "status": "no_guidance",
            "message": f"No direct Shariah ruling found for '{issue_key}'. Please consult a qualified scholar for nuanced cases."
        }

    def recommend_from_text(self, text: str) -> Dict[str, object]:
        """
        Lightweight keyword heuristic to map free-text to known issues.
        Returns first best match; extend to score multiple matches if needed.
        """
        t = (text or "").lower()
        for key, words in self._keyword_map.items():
            if any(w in t for w in words):
                out = self.recommend(key)
                out["detected_from"] = text
                return out
        return {
            "status": "no_guidance",
            "message": "No clear issue detected. Please rephrase or specify the concern (e.g., 'interest', 'backbiting')."
        }

    def list_topics(self) -> List[str]:
        return sorted(self.guidance_data.keys())

    def explain(self, issue_key: str) -> str:
        """
        Human-readable one-liner with ruling and sources.
        """
        r = self.recommend(issue_key)
        if r.get("status") == "guidance_found":
            return f"{r['issue']}: {r['ruling']} — {r['hadith']} | {r['quran_reference']}"
        return r["message"]

    # ---------------- Internals ----------------

    @staticmethod
    def _normalize_key(key: str) -> str:
        return (key or "").strip().lower().replace(" ", "_")
        

# ---------------- Quick self-test ----------------
if __name__ == "__main__":
    rec = ShariahGuidanceRecommender()
    print(rec.recommend("interest"))
    print(rec.recommend_from_text("I missed Fajr today and feel bad"))
    print(rec.explain("backbiting"))
    print("topics:", rec.list_topics())
