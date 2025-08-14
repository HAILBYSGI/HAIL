# core/deen_compliance_log.py
# HAIL — DeenComplianceLogger (Upgraded)

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Optional

try:
    from core.action_logger import ActionLogger
except Exception:  # pragma: no cover
    ActionLogger = None  # type: ignore


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DeenComplianceEntry:
    timestamp: str
    module: str
    action: str
    result: str
    deen_compliant: bool
    notes: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if d.get("meta") is None:
            d.pop("meta")
        if d.get("notes") is None:
            d.pop("notes")
        return d


class DeenComplianceLogger:
    """
    JSONL/JSON logger for Deen compliance events with:
      - atomic writes
      - thread safety
      - optional rotation (max_size_bytes)
      - simple query helpers for dashboards
      - optional ActionLogger + Mission Log mirroring
    """

    def __init__(
        self,
        log_file: str = "hail_logs/deen_compliance_log.json",
        *,
        max_size_bytes: int = 2_000_000,   # ~2MB before rotate
        keep_backups: int = 5,
        action_logger: Optional["ActionLogger"] = None,
        mission_log_sink: Optional[callable] = None,  # lambda d: mission_log.append(...)
    ) -> None:
        self.path = Path(log_file)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self.max_size = int(max_size_bytes)
        self.keep_backups = int(keep_backups)
        self.log = action_logger
        self.mission_log_sink = mission_log_sink

        if not self.path.exists():
            self._atomic_write([])

    # ------------- Public API -------------

    def log_entry(
        self,
        module: str,
        action: str,
        result: str,
        compliant: bool,
        *,
        notes: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Append a Deen compliance entry and mirror to sinks.
        """
        entry = DeenComplianceEntry(
            timestamp=_utc_iso(),
            module=module,
            action=action,
            result=result,
            deen_compliant=bool(compliant),
            notes=notes,
            meta=meta,
        )

        with self._lock:
            logs = self._read_all()
            logs.append(entry.to_dict())
            self._atomic_write(logs)

        # Sinks
        self._write_sinks(entry)
        return entry.to_dict()

    def get_latest_logs(self, count: int = 10) -> List[Dict[str, Any]]:
        with self._lock:
            logs = self._read_all()
            return logs[-int(count):]

    def get_by_module(self, module: str, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            logs = self._read_all()
            out = [x for x in reversed(logs) if x.get("module") == module]
            return list(reversed(out[:limit])) if out else []

    def since(self, iso_ts: str) -> List[Dict[str, Any]]:
        """
        Return entries with timestamp >= iso_ts.
        """
        with self._lock:
            logs = self._read_all()
            return [x for x in logs if str(x.get("timestamp", "")) >= iso_ts]

    def export_json(self) -> str:
        with self._lock:
            return json.dumps(self._read_all(), ensure_ascii=False)

    def clear(self) -> None:
        with self._lock:
            self._atomic_write([])

    # ------------- Internals -------------

    def _read_all(self) -> List[Dict[str, Any]]:
        try:
            with self.path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _atomic_write(self, data: List[Dict[str, Any]]) -> None:
        # rotate if large
        try:
            if self.path.exists() and self.path.stat().st_size > self.max_size:
                self._rotate()
        except Exception:
            pass

        tmp_fd, tmp_path = tempfile.mkstemp(prefix="deen_log_", suffix=".json", dir=str(self.path.parent))
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as tmp:
                json.dump(data, tmp, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.path)
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass

    def _rotate(self) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        backup = self.path.parent / f"deen_compliance_log.{ts}.json"
        try:
            shutil.copy2(self.path, backup)
            # prune old backups
            backups = sorted(self.path.parent.glob("deen_compliance_log.*.json"), reverse=True)
            for old in backups[self.keep_backups:]:
                try:
                    old.unlink()
                except OSError:
                    pass
        except Exception:
            pass

    def _write_sinks(self, entry: DeenComplianceEntry) -> None:
        # ActionLogger
        if self.log:
            try:
                self.log.log(
                    action_type="DeenCompliance",
                    decision="APPROVED" if entry.deen_compliant else "DENIED",
                    module=entry.module,
                    status="Success",
                    user_input=entry.action,
                    reason=entry.result[:300],
                    context={"deen_compliant": entry.deen_compliant},
                    meta=entry.meta or {},
                )
            except Exception:
                pass

        # MissionLog (optional)
        if self.mission_log_sink:
            try:
                verdict = "halal" if entry.deen_compliant else "haram"
                score = 0.05 if entry.deen_compliant else 0.75
                self.mission_log_sink(
                    {
                        "actor_id": "system:deen_compliance",
                        "activity": "deen_compliance_event",
                        "verdict": verdict,
                        "score": score,
                        "reasons": [entry.result[:120]],
                        "tags": ["compliance", entry.module],
                        "payload": entry.to_dict(),
                    }
                )
            except Exception:
                pass


# -------- Example usage --------
if __name__ == "__main__":
    logger = ActionLogger(also_print=True) if ActionLogger else None
    dcl = DeenComplianceLogger(action_logger=logger)
    dcl.log_entry("shariah_guard", "check: 'create music video'", "Blocked by policy", False, notes="music content")
    dcl.log_entry("quran_filter", "check: 'charity reminder'", "OK", True)
    print(dcl.get_latest_logs(2))
