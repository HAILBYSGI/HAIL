# core/founder_protocol.py
# HAIL — FounderProtocol (Upgraded)
from __future__ import annotations

import hmac
import hashlib
import json
import os
from dataclasses import dataclass
from typing import Optional, Callable, Dict

# Optional observability sink (best-effort)
try:
    from core.action_logger import ActionLogger  # type: ignore
except Exception:  # pragma: no cover
    ActionLogger = None  # type: ignore


def _ts_eq(a: str, b: str) -> bool:
    """Timing-safe equality (accepts None safely)."""
    a = (a or "").encode("utf-8")
    b = (b or "").encode("utf-8")
    return hmac.compare_digest(a, b)


def _hash_hex(value: str, *, salt: str = "") -> str:
    """
    Stable SHA-256 hex hash with optional salt (hex or utf-8 string).
    NOTE: Keep this deterministic for stored records. For stronger security,
    use a slow KDF (e.g., PBKDF2/argon2) in a dedicated auth service.
    """
    h = hashlib.sha256()
    if salt:
        h.update((salt if isinstance(salt, str) else str(salt)).encode("utf-8"))
    h.update((value or "").encode("utf-8"))
    return h.hexdigest()


@dataclass
class FounderSecrets:
    founder_name: str
    fingerprint_hash: str     # stored hash (already hashed with same method/salt)
    dna_hash: str             # stored hash (already hashed with same method/salt)
    salt: str = ""            # optional salt used when producing the stored hashes


class FounderProtocol:
    """
    Verifies Founder cryptographic markers (fingerprint, DNA).
    - Timing-safe comparisons
    - Optional OTP/2FA hook
    - ENV/JSON config loader for convenience
    - Optional ActionLogger + Mission Log sinks

    Backward-compatible methods:
      - verify_fingerprint(provided_fingerprint)
      - verify_dna(provided_dna)
      - is_authorized(provided_fingerprint, provided_dna)
    """

    def __init__(
        self,
        founder_name: str,
        fingerprint_hash: str,
        dna_hash: str,
        *,
        salt: str = "",
        otp_verifier: Optional[Callable[[], bool]] = None,
        mission_log_sink: Optional[Callable[[Dict], None]] = None,
    ) -> None:
        self._secrets = FounderSecrets(
            founder_name=founder_name,
            fingerprint_hash=fingerprint_hash,
            dna_hash=dna_hash,
            salt=salt or "",
        )
        self._otp_verifier = otp_verifier
        self._mission_log_sink = mission_log_sink

        # Optional ActionLogger
        self._action_logger = ActionLogger() if ActionLogger else None

    # ---------------- Factory helpers ----------------

    @classmethod
    def from_env(cls) -> "FounderProtocol":
        """
        Build from environment:
          HAIL_FOUNDER_NAME
          HAIL_FOUNDER_FP_HASH
          HAIL_FOUNDER_DNA_HASH
          HAIL_FOUNDER_SALT   (optional)
        """
        name = os.getenv("HAIL_FOUNDER_NAME", "Husnain Ali")
        fp = os.getenv("HAIL_FOUNDER_FP_HASH", "FINGERPRINT_HASH_PLACEHOLDER")
        dna = os.getenv("HAIL_FOUNDER_DNA_HASH", "DNA_HASH_PLACEHOLDER")
        salt = os.getenv("HAIL_FOUNDER_SALT", "")
        return cls(name, fp, dna, salt=salt)

    @classmethod
    def from_json(cls, path: str = "hail/config/founder_protocol.json") -> "FounderProtocol":
        """
        JSON format:
        {
          "founder_name": "...",
          "fingerprint_hash": "...",
          "dna_hash": "...",
          "salt": "optional"
        }
        """
        try:
            obj = json.loads(open(path, "r", encoding="utf-8").read())
        except FileNotFoundError:
            obj = {}
        return cls(
            obj.get("founder_name", "Husnain Ali"),
            obj.get("fingerprint_hash", "FINGERPRINT_HASH_PLACEHOLDER"),
            obj.get("dna_hash", "DNA_HASH_PLACEHOLDER"),
            salt=obj.get("salt", ""),
        )

    # ---------------- Public API (backward compatible) ----------------

    def verify_fingerprint(self, provided_fingerprint: str) -> bool:
        """
        Hashes `provided_fingerprint` with stored salt and compares (timing-safe)
        against the stored `fingerprint_hash`.
        """
        calc = _hash_hex(provided_fingerprint, salt=self._secrets.salt)
        ok = _ts_eq(calc, self._secrets.fingerprint_hash)
        self._observe("verify_fingerprint", ok, reason=f"calc={len(calc)}hex")
        return ok

    def verify_dna(self, provided_dna: str) -> bool:
        """
        Hashes `provided_dna` with stored salt and compares (timing-safe)
        against the stored `dna_hash`.
        """
        calc = _hash_hex(provided_dna, salt=self._secrets.salt)
        ok = _ts_eq(calc, self._secrets.dna_hash)
        self._observe("verify_dna", ok, reason=f"calc={len(calc)}hex")
        return ok

    def is_authorized(self, provided_fingerprint: str, provided_dna: str, *, require_otp: bool = False) -> bool:
        """
        Both markers must pass; if `require_otp` and an OTP verifier is supplied,
        it must also pass.
        """
        ok_fp = self.verify_fingerprint(provided_fingerprint)
        ok_dna = self.verify_dna(provided_dna)
        ok = bool(ok_fp and ok_dna)

        if ok and require_otp and self._otp_verifier:
            try:
                ok = bool(self._otp_verifier())
            except Exception:
                ok = False

        self._observe("is_authorized", ok, reason=f"fp={ok_fp} dna={ok_dna} otp={require_otp}")
        return ok

    # ---------------- Observability ----------------

    def _observe(self, action: str, ok: bool, *, reason: str = "") -> None:
        # ActionLogger
        if self._action_logger:
            try:
                self._action_logger.log(
                    action_type=f"FounderProtocol:{action}",
                    user_input="protected",
                    system_decision="ALLOW" if ok else "DENY",
                    module="founder_protocol",
                    reason=reason[:300],
                    status="Success",
                )
            except Exception:
                pass

        # Mission Log
        if self._mission_log_sink:
            try:
                self._mission_log_sink({
                    "actor_id": "system:auth",
                    "activity": action,
                    "verdict": "halal" if ok else "haram",
                    "score": 0.05 if ok else 0.85,
                    "reasons": [reason[:120]],
                    "tags": ["auth", "founder"],
                    "payload": {"ok": ok},
                })
            except Exception:
                pass


# ---------------- Minimal self-test ----------------
if __name__ == "__main__":
    # Example: create protocol from JSON (or use from_env())
    proto = FounderProtocol.from_json()

    # Suppose your stored JSON already holds salted hashes. Below we simulate:
    # salted_hash = _hash_hex("sample_fingerprint", salt=proto._secrets.salt)
    # print("Set this in config as fingerprint_hash:", salted_hash)

    print("Authorized?", proto.is_authorized("sample_fingerprint", "sample_dna"))
