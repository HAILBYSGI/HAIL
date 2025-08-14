# core/founder_identity.py
# HAIL — FounderIdentity (Upgraded)
from __future__ import annotations

import json
import os
import hmac
from dataclasses import dataclass, field, asdict
from threading import RLock
from typing import Callable, Dict, List, Optional


# Optional sinks (best‑effort; no hard dependency)
try:
    from core.action_logger import ActionLogger  # type: ignore
except Exception:  # pragma: no cover
    ActionLogger = None  # type: ignore


@dataclass
class FounderRecord:
    name: str = "Husnain Ali"
    fingerprint_hash: str = "FINGERPRINT_HASH_PLACEHOLDER"  # hex or opaque string
    dna_signature: str = "DNA_SIGNATURE_PLACEHOLDER"        # hex or opaque string
    authorized_devices: List[str] = field(default_factory=lambda: ["FounderPhone", "HAIL-Core-Device-001"])

    def to_dict(self) -> Dict:
        return asdict(self)


def _ts_eq(a: str, b: str) -> bool:
    """Timing‑safe equality for secrets (accepts None safely)."""
    a = a or ""
    b = b or ""
    # use bytes compare to avoid Unicode surprises
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


class FounderIdentity:
    """
    Verifies founder identity via (name, fingerprint hash, dna signature, device).
    Features:
      - Loads from ENV first, then JSON file (hail/config/founder_identity.json)
      - Timing‑safe comparisons for secret fields
      - Device registry management (add/remove/list)
      - Optional OTP/2FA hook for extra assurance
      - Optional sinks: ActionLogger + Mission Log
    """

    def __init__(
        self,
        *,
        config_path: str = "hail/config/founder_identity.json",
        otp_verifier: Optional[Callable[[], bool]] = None,         # e.g., lambda: verify_otp()
        mission_log_sink: Optional[Callable[[Dict], None]] = None, # lambda payload: mission_log.append(...)
    ) -> None:
        self._lock = RLock()
        self._path = config_path
        self._otp_verifier = otp_verifier
        self._mission_log_sink = mission_log_sink
        self._action_logger = ActionLogger() if ActionLogger else None

        self._rec = self._load_record()
        self._last_result: Optional[bool] = None  # simple cache for telemetry

    # ---------------- Public API ----------------

    def is_verified(self, input_name: str, fingerprint: str, dna: str, device: str, *, require_otp: bool = False) -> bool:
        """Primary verification method (backward compatible signature)."""
        with self._lock:
            ok_name = _ts_eq(input_name, self._rec.name)
            ok_fp = _ts_eq(fingerprint, self._rec.fingerprint_hash)
            ok_dna = _ts_eq(dna, self._rec.dna_signature)
            ok_dev = device in set(self._rec.authorized_devices)

            base_ok = bool(ok_name and ok_fp and ok_dna and ok_dev)

            if base_ok and require_otp and self._otp_verifier:
                try:
                    base_ok = bool(self._otp_verifier())
                except Exception:
                    base_ok = False

            self._last_result = base_ok

            # Sinks
            self._sink_action("FounderVerify", "SUCCESS" if base_ok else "FAIL",
                              reason=f"device={'ok' if ok_dev else 'no'} name={'ok' if ok_name else 'no'}")
            self._sink_mission(
                activity="founder_verify",
                verdict="halal" if base_ok else "haram",
                score=0.05 if base_ok else 0.85,
                reasons=[f"device_ok={ok_dev}", f"name_ok={ok_name}", f"fp_ok={ok_fp}", f"dna_ok={ok_dna}", f"otp={require_otp}"],
                payload={"device": device},
            )
            return base_ok

    # Convenience getters / admin ops
    def founder_name(self) -> str:
        return self._rec.name

    def list_devices(self) -> List[str]:
        return list(self._rec.authorized_devices)

    def authorize_device(self, device_name: str) -> None:
        with self._lock:
            if device_name not in self._rec.authorized_devices:
                self._rec.authorized_devices.append(device_name)
                self._persist()

    def revoke_device(self, device_name: str) -> None:
        with self._lock:
            self._rec.authorized_devices = [d for d in self._rec.authorized_devices if d != device_name]
            self._persist()

    def update_secrets(self, *, fingerprint_hash: Optional[str] = None, dna_signature: Optional[str] = None) -> None:
        with self._lock:
            if fingerprint_hash:
                self._rec.fingerprint_hash = fingerprint_hash
            if dna_signature:
                self._rec.dna_signature = dna_signature
            self._persist()

    # ---------------- Internals ----------------

    def _load_record(self) -> FounderRecord:
        # ENV (takes precedence if all present)
        env_email = os.getenv("HAIL_FOUNDER_NAME")
        env_fp = os.getenv("HAIL_FOUNDER_FINGERPRINT_HASH")
        env_dna = os.getenv("HAIL_FOUNDER_DNA_SIGNATURE")
        env_devices = os.getenv("HAIL_FOUNDER_DEVICES")  # comma-separated
        if env_email and env_fp and env_dna:
            devices = [x.strip() for x in (env_devices or "").split(",") if x.strip()] or ["FounderPhone", "HAIL-Core-Device-001"]
            return FounderRecord(name=env_email, fingerprint_hash=env_fp, dna_signature=env_dna, authorized_devices=devices)

        # JSON file fallback
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                obj = json.load(f)
            return FounderRecord(
                name=obj.get("name", "Husnain Ali"),
                fingerprint_hash=obj.get("fingerprint_hash", "FINGERPRINT_HASH_PLACEHOLDER"),
                dna_signature=obj.get("dna_signature", "DNA_SIGNATURE_PLACEHOLDER"),
                authorized_devices=list(obj.get("authorized_devices", ["FounderPhone", "HAIL-Core-Device-001"])),
            )
        except FileNotFoundError:
            # Create default config so ops can edit later
            default = FounderRecord()
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as w:
                json.dump(default.to_dict(), w, ensure_ascii=False, indent=2)
            return default

    def _persist(self) -> None:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as w:
            json.dump(self._rec.to_dict(), w, ensure_ascii=False, indent=2)

    # ---------------- Sinks ----------------

    def _sink_action(self, action_type: str, status: str, *, reason: str = "") -> None:
        if not self._action_logger:
            return
        try:
            self._action_logger.log(
                action_type=action_type,
                user_input="founder_identity_check",
                system_decision=status,
                module="founder_identity",
                reason=reason[:300],
                status="Success" if status == "SUCCESS" else "Denied",
            )
        except Exception:
            pass

    def _sink_mission(self, *, activity: str, verdict: str, score: float, reasons: List[str], payload: Dict) -> None:
        if not callable(self._mission_log_sink):
            return
        try:
            self._mission_log_sink({
                "actor_id": "system:auth",
                "activity": activity,
                "verdict": verdict,
                "score": float(score),
                "reasons": reasons,
                "tags": ["auth", "founder"],
                "payload": payload,
            })
        except Exception:
            pass


# -------------- Top‑level helper for legacy callers --------------

# Singleton (optional): import this and reuse across app if you want
_global_founder_identity = FounderIdentity()

def verify_founder(input_name: str, fingerprint: str, dna: str, device: str) -> bool:
    """
    Convenience wrapper so legacy code can call:
        from core.founder_identity import verify_founder
    """
    return _global_founder_identity.is_verified(input_name, fingerprint, dna, device)
