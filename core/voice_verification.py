# core/voice_verification.py
# Phase 1 — Founder Voice Trigger Verification
# - Verifies activation phrase + voiceprint hash
# - Supports bytes OR file path inputs
# - Loads registered voiceprint from config if available
# - Returns a structured result (ok/phrase_ok/voice_ok/reason)
# - Backward-compatible shim: verify_voice(...)

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Optional


DEFAULT_TRIGGER = "Bismillah, HAIL begins"
DEFAULT_HASH = "VOICEPRINT_HASH_PLACEHOLDER"  # replace in production
CONFIG_PATH = os.path.join("hail", "config", "voiceprint.key")  # one-line file with the hex hash


@dataclass
class VoiceVerifyResult:
    ok: bool
    phrase_ok: bool
    voice_ok: bool
    reason: str

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "phrase_ok": self.phrase_ok,
            "voice_ok": self.voice_ok,
            "reason": self.reason,
        }


class VoiceVerifier:
    def __init__(self,
                 expected_trigger_phrase: str = DEFAULT_TRIGGER,
                 registered_voiceprint_hash: Optional[str] = None,
                 config_path: str = CONFIG_PATH) -> None:
        self.expected_trigger_phrase = expected_trigger_phrase.strip()

        # Load voiceprint hash from config if not provided
        self.registered_voiceprint_hash = (registered_voiceprint_hash or
                                           self._load_hash_from_config(config_path) or
                                           DEFAULT_HASH)

    # ---------- public API ----------
    def verify(self,
               spoken_phrase: str,
               audio_bytes: Optional[bytes] = None,
               audio_path: Optional[str] = None) -> VoiceVerifyResult:
        """
        Verify both phrase and voiceprint.
        - Provide either `audio_bytes` OR `audio_path` (file will be read as bytes).
        """
        # Phrase check (exact match by design; adjust to allow minor diff if needed)
        phrase_ok = (spoken_phrase or "").strip() == self.expected_trigger_phrase

        # Voice check
        voice_ok = False
        audio_buf: Optional[bytes] = audio_bytes

        if audio_buf is None and audio_path:
            try:
                with open(audio_path, "rb") as f:
                    audio_buf = f.read()
            except Exception:
                audio_buf = None

        if audio_buf:
            voice_ok = self._hash_audio(audio_buf) == self.registered_voiceprint_hash

        # Decide
        if phrase_ok and voice_ok:
            return VoiceVerifyResult(True, True, True, "Founder voice trigger verified.")
        if not phrase_ok and not voice_ok:
            return VoiceVerifyResult(False, False, False, "Phrase mismatch and voiceprint mismatch.")
        if not phrase_ok:
            return VoiceVerifyResult(False, False, voice_ok, "Phrase mismatch.")
        return VoiceVerifyResult(False, True, False, "Voiceprint mismatch.")

    # ---------- helpers ----------
    @staticmethod
    def _hash_audio(audio_bytes: bytes) -> str:
        """
        Simulated voiceprint hash using SHA-256.
        Replace with a real speaker-embedding pipeline in production.
        """
        return hashlib.sha256(audio_bytes).hexdigest()

    @staticmethod
    def _load_hash_from_config(path: str) -> Optional[str]:
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return f.read().strip()
        except Exception:
            pass
        return None


# ---------- Backward-compatible shim ----------
# Some older code might `from voice_verification import verify_voice`
def verify_voice(audio_bytes_or_path, spoken_phrase) -> bool:
    """
    Legacy boolean API:
    - If `audio_bytes_or_path` is bytes → treat as bytes
    - If it is a string path → load file bytes
    Returns True/False only.
    """
    v = VoiceVerifier()
    if isinstance(audio_bytes_or_path, (bytes, bytearray)):
        res = v.verify(spoken_phrase=spoken_phrase, audio_bytes=bytes(audio_bytes_or_path))
    elif isinstance(audio_bytes_or_path, str):
        res = v.verify(spoken_phrase=spoken_phrase, audio_path=audio_bytes_or_path)
    else:
        res = VoiceVerifyResult(False, False, False, "Invalid audio input type.")
    return res.ok


# ---------- Self-test ----------
if __name__ == "__main__":
    verifier = VoiceVerifier()
    # Demo with wrong inputs (since placeholders are used)
    print(verifier.verify("Bismillah, HAIL begins", audio_bytes=b"fake_wav").to_dict())
    print(verify_voice(b"fake_wav", "Bismillah, HAIL begins"))
