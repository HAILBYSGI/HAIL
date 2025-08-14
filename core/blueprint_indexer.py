# core/blueprint_indexer.py
# Part of HAIL Phase 2 – Memory & Indexing Engine (Upgraded)

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Dict, Any, List, Optional

try:
    from core.action_logger import ActionLogger
except Exception:  # pragma: no cover
    ActionLogger = None  # type: ignore

_PHASE_ID_RE = re.compile(r"^\s*Phase[\s_]+(\d+(?:\.\d+)?)\s*$", re.IGNORECASE)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PhaseRecord:
    phase_id: str
    data: Dict[str, Any]
    created_at: str
    updated_at: str
    version: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BlueprintIndexer:
    """
    JSON store for HAIL blueprint phases with atomic writes, versioning, and search.
    Layout:
      hail_data/blueprints.json          # single JSON dict: {phase_id: PhaseRecord}
      hail_data/blueprints_backups/      # rotated backups on each write (optional)
    """

    def __init__(
        self,
        memory_path: str = "hail_data/blueprints.json",
        *,
        keep_backups: int = 5,
        action_logger: Optional["ActionLogger"] = None,
    ) -> None:
        self.memory_path = Path(memory_path)
        self.keep_backups = keep_backups
        self._lock = RLock()
        self.log = action_logger

        self._ensure_file()

    # ---------- filesystem helpers ----------

    @property
    def _backup_dir(self) -> Path:
        return self.memory_path.parent / "blueprints_backups"

    def _ensure_file(self) -> None:
        with self._lock:
            self.memory_path.parent.mkdir(parents=True, exist_ok=True)
            if not self.memory_path.exists():
                self._atomic_write({})

    def _load_all(self) -> Dict[str, Any]:
        with self._lock:
            try:
                with self.memory_path.open("r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}

    def _atomic_write(self, data: Dict[str, Any]) -> None:
        """Write atomically and rotate a small backup."""
        tmp_fd, tmp_path = tempfile.mkstemp(prefix="bp_", suffix=".json", dir=str(self.memory_path.parent))
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as tmp:
                json.dump(data, tmp, ensure_ascii=False, indent=2)
            # backup the old file (if exists)
            if self.memory_path.exists():
                self._backup_dir.mkdir(parents=True, exist_ok=True)
                ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
                backup = self._backup_dir / f"blueprints.{ts}.json"
                shutil.copy2(self.memory_path, backup)
                # cleanup older backups
                backups = sorted(self._backup_dir.glob("blueprints.*.json"), reverse=True)
                for old in backups[self.keep_backups :]:
                    try:
                        old.unlink()
                    except OSError:
                        pass
            # atomic replace
            os.replace(tmp_path, self.memory_path)
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass

    # ---------- validation ----------

    def _normalize_phase_id(self, phase_id: str) -> str:
        """Normalize forms like 'Phase_3.50' or 'Phase 3.50' to 'Phase 3.50'."""
        m = _PHASE_ID_RE.match(phase_id.strip())
        if not m:
            # accept raw key but still normalize whitespace
            return phase_id.strip()
        return f"Phase {m.group(1)}"

    # ---------- public API ----------

    def load_blueprints(self) -> Dict[str, Any]:
        return self._load_all()

    def exists(self, phase_id: str) -> bool:
        pid = self._normalize_phase_id(phase_id)
        return pid in self._load_all()

    def save_blueprint(self, phase_id: str, blueprint_data: Dict[str, Any]) -> bool:
        """
        Upsert a blueprint. Adds timestamps and bumps version if record exists.
        """
        pid = self._normalize_phase_id(phase_id)
        with self._lock:
            all_data = self._load_all()
            prev = all_data.get(pid)
            now = _utc_iso()

            if prev and isinstance(prev, dict) and "version" in prev:
                rec = PhaseRecord(
                    phase_id=pid,
                    data=blueprint_data,
                    created_at=prev.get("created_at", now),
                    updated_at=now,
                    version=int(prev.get("version", 1)) + 1,
                )
            else:
                rec = PhaseRecord(
                    phase_id=pid, data=blueprint_data, created_at=now, updated_at=now, version=1
                )

            all_data[pid] = rec.to_dict()
            try:
                self._atomic_write(all_data)
                if self.log:
                    self.log.log(
                        action_type="BlueprintIndex",
                        decision="APPROVED",
                        module="blueprint_indexer",
                        status="Success",
                        reason=f"Saved {pid} v{rec.version}",
                        context={"phase_id": pid, "version": rec.version},
                    )
                return True
            except Exception as e:
                if self.log:
                    self.log.log(
                        action_type="BlueprintIndex",
                        decision="ERROR",
                        module="blueprint_indexer",
                        status="Failure",
                        reason=str(e),
                        context={"phase_id": pid},
                    )
                return False

    def get_blueprint(self, phase_id: str) -> Dict[str, Any]:
        pid = self._normalize_phase_id(phase_id)
        return self._load_all().get(pid, {})

    def delete_phase(self, phase_id: str) -> bool:
        pid = self._normalize_phase_id(phase_id)
        with self._lock:
            all_data = self._load_all()
            if pid not in all_data:
                return False
            del all_data[pid]
            try:
                self._atomic_write(all_data)
                if self.log:
                    self.log.log(
                        action_type="BlueprintIndex",
                        decision="APPROVED",
                        module="blueprint_indexer",
                        status="Success",
                        reason=f"Deleted {pid}",
                        context={"phase_id": pid},
                    )
                return True
            except Exception:
                return False

    def list_all_phases(self, *, sort_numeric: bool = True) -> List[str]:
        keys = list(self._load_all().keys())
        if not sort_numeric:
            return sorted(keys)
        # sort by numeric part when available (e.g., Phase 3.49 before Phase 3.5?)
        def keyfn(k: str):
            m = _PHASE_ID_RE.match(k)
            return float(m.group(1)) if m else float("inf")
        return sorted(keys, key=keyfn)

    def search(self, text: str, *, in_keys: bool = True, in_values: bool = True) -> List[str]:
        """
        Simple case-insensitive search over phase ids and/or JSON stringified values.
        Returns list of matching phase ids.
        """
        t = text.lower().strip()
        if not t:
            return []
        out: List[str] = []
        data = self._load_all()
        for pid, rec in data.items():
            hit = False
            if in_keys and t in pid.lower():
                hit = True
            elif in_values:
                try:
                    s = json.dumps(rec, ensure_ascii=False).lower()
                    if t in s:
                        hit = True
                except Exception:
                    pass
            if hit:
                out.append(pid)
        return out

    def export_all(self) -> Dict[str, Any]:
        """Return the whole index (useful for backup or debugging)."""
        return self._load_all()

    def import_all(self, payload: Dict[str, Any], *, overwrite: bool = False) -> bool:
        """
        Import a complete index. If overwrite=False, merges and bumps versions.
        """
        with self._lock:
            current = self._load_all()
            now = _utc_iso()
            for raw_pid, rec in payload.items():
                pid = self._normalize_phase_id(raw_pid)
                existing = current.get(pid)
                if overwrite or not existing:
                    # trust incoming, but ensure required fields
                    v = int(rec.get("version", 1))
                    created = rec.get("created_at") or now
                    current[pid] = {
                        "phase_id": pid,
                        "data": rec.get("data", {}),
                        "created_at": created,
                        "updated_at": now,
                        "version": v,
                    }
                else:
                    # merge: keep existing, bump version, update data
                    v = int(existing.get("version", 1)) + 1
                    current[pid] = {
                        "phase_id": pid,
                        "data": rec.get("data", existing.get("data", {})),
                        "created_at": existing.get("created_at", now),
                        "updated_at": now,
                        "version": v,
                    }

            try:
                self._atomic_write(current)
                if self.log:
                    self.log.log(
                        action_type="BlueprintIndex",
                        decision="APPROVED",
                        module="blueprint_indexer",
                        status="Success",
                        reason=f"Imported {len(payload)} phases",
                    )
                return True
            except Exception as e:
                if self.log:
                    self.log.log(
                        action_type="BlueprintIndex",
                        decision="ERROR",
                        module="blueprint_indexer",
                        status="Failure",
                        reason=str(e),
                    )
                return False


# Example usage:
if __name__ == "__main__":
    logger = ActionLogger(also_print=True) if ActionLogger else None
    bi = BlueprintIndexer(action_logger=logger)

    example_data = {"purpose": "Phase 2.2 test", "modules": ["storage", "access"]}
    bi.save_blueprint("Phase_2.2", example_data)
    bi.save_blueprint("Phase 3.50", {"purpose": "Refresher hooks", "ethics": ["no_riba", "no_haram"]})

    print("All phases:", bi.list_all_phases())
    print("Search 'refresher':", bi.search("refresher"))
    print("Get P3.50:", bi.get_blueprint("Phase 3.50"))
