# core/trust_validator.py
# Phase 3 — Trust & Security: Multi-factor trust scoring with clear reasons.
# Backward compatible with your previous API (is_trusted, trust_report),
# but adds: configurable weights/threshold, reason breakdown, and helpers.

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Set, Tuple


@dataclass
class TrustFactors:
    founder_bonus: int = 5
    token_weight: int = 3
    device_weight: int = 3
    voice_weight: int = 4
    recent_token_bonus: int = 1          # small extra if token is very recent
    recent_token_window: int = 15        # minutes


@dataclass
class TrustPolicy:
    pass_threshold: int = 6              # minimum points to be trusted
    warn_threshold: int = 4              # below this, flag as weak
    # You can add per-context policies later (e.g., write vs read)


class TrustValidator:
    def __init__(self, policy: Optional[TrustPolicy] = None, factors: Optional[TrustFactors] = None):
        self.policy = policy or TrustPolicy()
        self.factors = factors or TrustFactors()

        self.verified_tokens: Set[str] = set()
        self.verified_devices: Set[str] = set()
        self.verified_voiceprints: Dict[str, str] = {}

        # Track issuance times for tokens (optional bonus for freshness)
        self._token_issued_at: Dict[str, datetime] = {}

        # Founder id (can be adapted to your identity module)
        self.founder_id = "husnain.ali"

    # ---------- registration helpers ----------
    def add_verified_token(self, token: str, issued_at: Optional[datetime] = None):
        self.verified_tokens.add(token)
        self._token_issued_at[token] = issued_at or datetime.now(timezone.utc)

    def add_verified_voice(self, user_id: str, voice_hash: str):
        self.verified_voiceprints[user_id] = voice_hash

    def add_verified_device(self, device_id: str):
        self.verified_devices.add(device_id)

    # ---------- core checks ----------
    def _score(self, user_id: str, device_id: Optional[str], token: Optional[str], voice_hash: Optional[str]) -> Tuple[int, Dict[str, int]]:
        reasons: Dict[str, int] = {}

        # Founder bonus (identity alignment)
        if user_id == self.founder_id:
            reasons["founder_bonus"] = self.factors.founder_bonus

        # Token factor (+ freshness bonus)
        if token and token in self.verified_tokens:
            reasons["token_weight"] = self.factors.token_weight
            t_issued = self._token_issued_at.get(token)
            if t_issued:
                age = datetime.now(timezone.utc) - t_issued
                if age <= timedelta(minutes=self.factors.recent_token_window):
                    reasons["recent_token_bonus"] = self.factors.recent_token_bonus

        # Device factor
        if device_id and device_id in self.verified_devices:
            reasons["device_weight"] = self.factors.device_weight

        # Voiceprint factor
        if voice_hash and self.verified_voiceprints.get(user_id) == voice_hash:
            reasons["voice_weight"] = self.factors.voice_weight

        total = sum(reasons.values())
        return total, reasons

    def is_trusted(self, user_id: str, device_id: Optional[str] = None,
                   token: Optional[str] = None, voice_hash: Optional[str] = None) -> bool:
        total, _ = self._score(user_id, device_id, token, voice_hash)
        return total >= self.policy.pass_threshold

    def trust_report(self, user_id: str, device_id: Optional[str] = None,
                     token: Optional[str] = None, voice_hash: Optional[str] = None) -> Dict[str, object]:
        total, breakdown = self._score(user_id, device_id, token, voice_hash)

        if total >= self.policy.pass_threshold:
            level = "TRUSTED"
            note = "Source validated and authorized for HAIL execution."
        elif total >= self.policy.warn_threshold:
            level = "WEAK_TRUST"
            note = "Meets some factors but below full trust; restrict sensitive actions."
        else:
            level = "UNTRUSTED"
            note = "Source failed to meet trust requirements. Execution denied."

        return {
            "status": level,
            "score": total,
            "thresholds": {
                "pass": self.policy.pass_threshold,
                "warn": self.policy.warn_threshold
            },
            "breakdown": breakdown,          # which factors contributed
            "subject": {
                "user_id": user_id,
                "device_id": device_id,
                "has_token": bool(token),
                "has_voice": bool(voice_hash),
            },
            "message": note
        }


# ---------------- quick self-test ----------------
if __name__ == "__main__":
    tv = TrustValidator()
    tv.add_verified_token("12345")                           # issued now (fresh)
    tv.add_verified_device("raspi-01")
    tv.add_verified_voice("husnain.ali", "voicehash001")

    print(tv.trust_report("husnain.ali", "raspi-01", "12345", "voicehash001"))
    print(tv.trust_report("guest", "raspi-01", "badtoken", None))
