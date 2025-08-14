# core/memory_store.py
# HAIL — Durable JSON key-value store (backward compatible)
from __future__ import annotations

import json
import os
import shutil
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional


# ---------- Paths ----------
DATA_DIR = os.path.join("hail", "data")
LOG_DIR = os.path.join("hail", "logs")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

MEMORY_FILE = os.path.join(DATA_DIR, "hail_memory.json")
AUDIT_FILE = os.path.join(LOG_DIR, "memory_audit.jsonl")


# ---------- Utilities ----------
_LOCK = threading.RLock()
_MAX_BYTES = 2_000_000  # ~2 MB soft cap for the JSON blob (adjust later)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_write_json(path: str, obj: Any) -> None:
    """Atomic write: write to temp then replace."""
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _backup_snapshot() -> Optional[str]:
    """Create a timestamped backup of the current memory file if it exists."""
    if not os.path.exists(MEMORY_FILE):
        return None
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bpath = os.path.join(BACKUP_DIR, f"hail_memory_{ts}.json")
    shutil.copy2(MEMORY_FILE, bpath)
    # Keep last 10 backups
    snaps = sorted([p for p in os.listdir(BACKUP_DIR) if p.endswith(".json")])
    if len(snaps) > 10:
        for p in snaps[:-10]:
            try:
                os.remove(os.path.join(BACKUP_DIR, p))
            except Exception:
                pass
    return bpath


def _audit(event: str, payload: Dict[str, Any]) -> None:
    try:
        row = {"ts": _utc(), "event": event, **payload}
        with open(AUDIT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        # best-effort; never fail the write because of audit
        pass


def _validate_key(key: str) -> None:
    if not isinstance(key, str) or not key:
        raise ValueError("Key must be a non-empty string.")
    if len(key) > 256:
        raise ValueError("Key too long (>256).")
    # Reserve simple namespace pattern "ns:key" for internal use
    # but allow plain keys for backward compatibility.


def _size_okay(obj: Dict[str, Any]) -> bool:
    try:
        blob = json.dumps(obj, ensure_ascii=False)
        return len(blob.encode("utf-8")) <= _MAX_BYTES
    except Exception:
        return False


# Ensure file exists
if not os.path.exists(MEMORY_FILE):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump({}, f)


# ---------- Core Store ----------
class MemoryStore:
    """
    JSON file-backed KV store with atomic writes, backups, and audit trail.
    Backward compatible wrapper functions are provided below.
    """
    def __init__(self, founder_checker: Optional[Callable[[], bool]] = None) -> None:
        self._founder_checker = founder_checker

    def _load(self) -> Dict[str, Any]:
        with _LOCK:
            try:
                with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f) or {}
            except json.JSONDecodeError:
                # Corrupt file; try to recover from the most recent backup
                _audit("corrupt_memory", {"path": MEMORY_FILE})
                snaps = sorted(
                    [os.path.join(BACKUP_DIR, p) for p in os.listdir(BACKUP_DIR) if p.endswith(".json")],
                    reverse=True
                )
                for snap in snaps:
                    try:
                        with open(snap, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        _safe_write_json(MEMORY_FILE, data)
                        _audit("restore_from_backup", {"backup": snap})
                        return data
                    except Exception:
                        continue
                # If no backup works, reset
                _audit("reset_memory", {})
                _safe_write_json(MEMORY_FILE, {})
                return {}
            except FileNotFoundError:
                _safe_write_json(MEMORY_FILE, {})
                return {}

    def _save(self, data: Dict[str, Any]) -> None:
        with _LOCK:
            if not _size_okay(data):
                raise ValueError("Refusing to write: memory size exceeds safe quota.")
            _backup_snapshot()
            _safe_write_json(MEMORY_FILE, data)

    def get(self, key: str, *, namespace: Optional[str] = None) -> Any:
        _validate_key(key)
        data = self._load()
        if namespace:
            return data.get(namespace, {}).get(key)
        return data.get(key)

    def set(
        self,
        key: str,
        value: Any,
        *,
        founder_authenticated: bool = False,
        namespace: Optional[str] = None,
    ) -> None:
        _validate_key(key)
        if not founder_authenticated and not self._is_founder():
            raise PermissionError("Only verified Founder may modify HAIL memory.")

        with _LOCK:
            data = self._load()
            if namespace:
                if namespace not in data or not isinstance(data[namespace], dict):
                    data[namespace] = {}
                data[namespace][key] = value
            else:
                data[key] = value
            self._save(data)
        _audit("set", {"key": key, "ns": namespace, "type": type(value).__name__})

    def delete(self, key: str, *, founder_authenticated: bool = False, namespace: Optional[str] = None) -> bool:
        _validate_key(key)
        if not founder_authenticated and not self._is_founder():
            raise PermissionError("Only verified Founder may delete memory.")
        removed = False
        with _LOCK:
            data = self._load()
            if namespace:
                ns = data.get(namespace, {})
                if key in ns:
                    ns.pop(key, None)
                    data[namespace] = ns
                    removed = True
            else:
                if key in data:
                    data.pop(key, None)
                    removed = True
            if removed:
                self._save(data)
        _audit("delete", {"key": key, "ns": namespace, "removed": removed})
        return removed

    def list_keys(self, *, namespace: Optional[str] = None) -> Dict[str, Any]:
        data = self._load()
        if namespace:
            ns = data.get(namespace, {})
            return {"namespace": namespace, "keys": list(ns.keys())}
        return {"keys": list(data.keys())}

    def all(self) -> Dict[str, Any]:
        return self._load()

    # ---------- Founder auth ----------
    def _is_founder(self) -> bool:
        if callable(self._founder_checker):
            try:
                return bool(self._founder_checker())
            except Exception:
                return False
        return False


# Singleton store with optional external founder checker (wire later if needed)
_STORE = MemoryStore()


# ---------- Backward-compatible module functions ----------
def load_memory() -> Dict[str, Any]:
    return _STORE.all()


def save_memory(data: Dict[str, Any]) -> None:
    _STORE._save(data)  # atomic + backup + quota


def get(key: str) -> Any:
    return _STORE.get(key)


def set(key: str, value: Any, founder_authenticated: bool = False) -> None:
    _STORE.set(key, value, founder_authenticated=founder_authenticated)


def delete(key: str, founder_authenticated: bool = False) -> None:
    _STORE.delete(key, founder_authenticated=founder_authenticated)


# -------- Optional: namespaced helpers (non-breaking) --------
def nget(namespace: str, key: str) -> Any:
    return _STORE.get(key, namespace=namespace)


def nset(namespace: str, key: str, value: Any, founder_authenticated: bool = False) -> None:
    _STORE.set(key, value, founder_authenticated=founder_authenticated, namespace=namespace)


def ndelete(namespace: str, key: str, founder_authenticated: bool = False) -> bool:
    return _STORE.delete(key, founder_authenticated=founder_authenticated, namespace=namespace)


def nlist(namespace: str) -> Dict[str, Any]:
    return _STORE.list_keys(namespace=namespace)
