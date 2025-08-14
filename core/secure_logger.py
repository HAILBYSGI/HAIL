# core/secure_logger.py
# Part of HAIL Phase 3 – AI Ethics, Command & Security Logic
# Secure, append-only, tamper-evident logging with optional encryption.
#
# Features
# - Encrypts entries with Fernet (if available), else falls back to plaintext+HMAC
# - HMAC-SHA256 integrity on every log line (detects tampering/corruption)
# - Key file stores both encryption and HMAC keys
# - Utilities: read_logs(), verify_line(), rotate_keys(), list_days()
#
# Log line format (one JSON object per line):
# {
#   "alg": "fernet+hmac" | "plain+hmac",
#   "blob": "<base64 or json string>",
#   "hmac": "<hex>",
#   "ts": "<ISO timestamp>"
# }

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple

# ---- Optional encryption dependency
try:
    from cryptography.fernet import Fernet  # type: ignore
    _HAS_FERNET = True
except Exception:  # cryptography not installed
    Fernet = None  # type: ignore
    _HAS_FERNET = False


@dataclass
class _Keys:
    enc_key_b64: Optional[str]   # base64 urlsafe Fernet key, or None
    hmac_key_hex: str            # hex string of HMAC key

class SecureLogger:
    def __init__(self,
                 key_file: str = 'core/logger_key.json',
                 log_dir: str = 'logs'):
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        self.key_file = key_file
        self.keys = self._load_or_create_keys()
        self._fernet = Fernet(self.keys.enc_key_b64.encode()) if (_HAS_FERNET and self.keys.enc_key_b64) else None

    # ------------------------- Public API -------------------------

    def log(self, module: str, action: str, status: str, metadata: Optional[Dict] = None) -> bool:
        """
        Append a secure log line (encrypted if cryptography is installed).
        Returns True on success.
        """
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "module": module,
            "action": action,
            "status": status,
            "metadata": metadata or {}
        }
        line = self._pack_line(entry)
        filename = self._day_path(datetime.utcnow().date())
        with open(filename, 'ab') as f:
            f.write(line + b'\n')
        return True

    def read_logs(self, target_day: Optional[date] = None) -> List[Dict]:
        """
        Read and verify all entries for the specified day (default: today).
        Returns list of dict entries (verified only).
        """
        target_day = target_day or datetime.utcnow().date()
        path = self._day_path(target_day)
        entries: List[Dict] = []
        if not os.path.exists(path):
            return entries

        with open(path, 'rb') as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                ok, obj = self.verify_line(raw)
                if not ok:
                    # Skip corrupted/tampered lines
                    continue
                entries.append(obj)
        return entries

    def list_days(self) -> List[str]:
        """Return YYYY-MM-DD filenames present in the log directory."""
        if not os.path.isdir(self.log_dir):
            return []
        out = []
        for name in os.listdir(self.log_dir):
            if name.startswith("log_") and name.endswith(".log"):
                out.append(name[len("log_"):-len(".log")])
        return sorted(out)

    def rotate_keys(self) -> Dict[str, str]:
        """
        Generate new encryption + HMAC keys.
        New writes use the new keys. Old log lines remain readable ONLY if you
        keep a backup of the previous key file. (This is standard practice.)
        """
        self.keys = self._create_keys(overwrite=True)
        self._fernet = Fernet(self.keys.enc_key_b64.encode()) if (_HAS_FERNET and self.keys.enc_key_b64) else None
        return {"status": "rotated", "encryption": "enabled" if self._fernet else "disabled"}

    # ------------------------- Verification -------------------------

    def verify_line(self, raw_line: bytes) -> Tuple[bool, Dict]:
        """
        Verify HMAC and decode/decrypt a single line.
        Returns (ok, obj). If ok is False, obj may contain an error.
        """
        try:
            wrapper = json.loads(raw_line.decode('utf-8'))
            alg = wrapper.get("alg")
            blob = wrapper.get("blob")
            tag = wrapper.get("hmac", "")
            ts = wrapper.get("ts")

            # Recompute HMAC and compare
            mac = self._hmac_digest((alg or "") + "|" + (blob or "") + "|" + (ts or ""))
            if not hmac.compare_digest(mac, tag):
                return False, {"error": "HMAC_MISMATCH"}

            # Decrypt / parse
            if alg == "fernet+hmac":
                if not self._fernet:
                    return False, {"error": "FERNET_UNAVAILABLE_FOR_DECRYPT"}
                data = self._fernet.decrypt(base64.urlsafe_b64decode(blob.encode('utf-8')))
                obj = json.loads(data.decode('utf-8'))
            elif alg == "plain+hmac":
                # blob is base64 of utf-8 json string
                data = base64.urlsafe_b64decode(blob.encode('utf-8'))
                obj = json.loads(data.decode('utf-8'))
            else:
                return False, {"error": "UNKNOWN_ALG"}

            return True, obj
        except Exception as e:
            return False, {"error": repr(e)}

    # ------------------------- Internals -------------------------

    def _pack_line(self, obj: Dict) -> bytes:
        ts = datetime.utcnow().isoformat()
        if self._fernet:
            # Encrypt JSON then base64-encode the ciphertext for storage
            plaintext = json.dumps(obj, separators=(',', ':')).encode('utf-8')
            token = self._fernet.encrypt(plaintext)  # already URL-safe base64 bytes
            blob = base64.urlsafe_b64encode(token).decode('utf-8')
            alg = "fernet+hmac"
        else:
            # Fallback: plaintext JSON base64 (still HMAC-protected)
            raw = json.dumps(obj, separators=(',', ':')).encode('utf-8')
            blob = base64.urlsafe_b64encode(raw).decode('utf-8')
            alg = "plain+hmac"

        tag = self._hmac_digest(f"{alg}|{blob}|{ts}")
        wrapper = {"alg": alg, "blob": blob, "hmac": tag, "ts": ts}
        return json.dumps(wrapper, ensure_ascii=False).encode('utf-8')

    def _hmac_digest(self, msg: str) -> str:
        key = bytes.fromhex(self.keys.hmac_key_hex)
        return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).hexdigest()

    def _day_path(self, d: date) -> str:
        return os.path.join(self.log_dir, f"log_{d.isoformat()}.log")

    # ------------------------- Key handling -------------------------

    def _load_or_create_keys(self) -> _Keys:
        if os.path.exists(self.key_file):
            try:
                with open(self.key_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return _Keys(
                    enc_key_b64=data.get("encryption_key_b64"),
                    hmac_key_hex=data["hmac_key_hex"],
                )
            except Exception:
                # If corrupted, re-create
                return self._create_keys(overwrite=True)
        return self._create_keys(overwrite=False)

    def _create_keys(self, overwrite: bool) -> _Keys:
        enc_key_b64 = None
        if _HAS_FERNET:
            # Generate a Fernet key (base64 urlsafe)
            from cryptography.fernet import Fernet as F  # type: ignore
            enc_key_b64 = F.generate_key().decode('utf-8')

        # HMAC key (32 bytes)
        hmac_key = os.urandom(32).hex()
        data = {"encryption_key_b64": enc_key_b64, "hmac_key_hex": hmac_key}

        os.makedirs(os.path.dirname(self.key_file) or ".", exist_ok=True)
        with open(self.key_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

        return _Keys(enc_key_b64=enc_key_b64, hmac_key_hex=hmac_key)


# ------------------------- Example usage -------------------------
if __name__ == "__main__":
    logger = SecureLogger()
    logger.log(
        module="ActionBlocker",
        action="Blocked non-halal command",
        status="BLOCKED",
        metadata={"command": "Play music", "reason": "Shari’ah violation"}
    )
    logger.log(
        module="CommandHandler",
        action="Allowed halal task",
        status="OK",
        metadata={"task": "Schedule zakat reminders"}
    )

    print("Days:", logger.list_days())
    print("Today entries:", logger.read_logs())
