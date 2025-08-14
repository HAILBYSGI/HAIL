# core/founder_trace.py
# HAIL — FounderTrace (Upgraded)
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Optional


# Optional sink (best‑effort)
try:
    from core.action_logger import ActionLogger  # type: ignore
except Exception:  # pragma: no cover
    ActionLogger = None  # type: ignore


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_str(s: str) -> str:
    return sha256(s.encode("utf-8")).hexdigest()


@dataclass
class FounderTraceEntry:
    timestamp: str
    module: str
    action: str
    source: str = "unknown"
    override: bool = False
    verified_founder: bool = False
    checksum: str = ""  # integrity of the core fields

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def make_checksum(module: str, action: str, source: str, override: bool, verified: bool, ts: str) -> str:
        payload = json.dumps(
            {"ts": ts, "m": module, "a": action, "s": source, "o": override, "v": verified},
            sort_keys=True,
            ensure_ascii=False,
        )
        return _hash_str(payload)


class FounderTrace:
    """
    Founder activity trace with persistence and integrity checksum.
    Backward‑compatible API:
      - log_action(module, action, source="unknown", override=False)
      - get_all_logs()
      - get_logs_by_module(module_name)
      - get_logs_by_source(source_id)
      - verify_last_action()
    New:
      - tail(n), export_json(), filter(...), verify_integrity()
      - JSONL log with rotation; optional sinks: ActionLogger & Mission Log
    """

    def __init__(
        self,
        founder_id: str = "husnain_ali",
        *,
        jsonl_path: str = "hail/logs/founder_trace.jsonl",
        max_bytes: int = 2_000_000,
        keep_backups: int = 5,
        mission_log_sink: Optional[callable] = None,  # lambda payload: mission_log.append(...)
    ) -> None:
        self.founder_id = founder_id
        self._jsonl = Path(jsonl_path)
        self._jsonl.parent.mkdir(parents=True, exist_ok=True)
        self._max_bytes = int(max_bytes)
        self._keep_backups = int(keep_backups)
        self._lock = RLock()
        self._cache: List[Dict[str, Any]] = []  # in-memory recent entries

        self._mission_log_sink = mission_log_sink
        self._action_logger = ActionLogger() if ActionLogger else None

    # ---------------- Backward‑compatible methods ----------------

    def log_action(self, module: str, action: str, source: str = "unknown", override: bool = False) -> Dict[str, Any]:
        verified = (source == self.founder_id)
        ts = _utc_iso()
        checksum = FounderTraceEntry.make_checksum(module, action, source, override, verified, ts)

        entry = FounderTraceEntry(
            timestamp=ts,
            module=str(module),
            action=str(action),
            source=str(source),
            override=bool(override),
            verified_founder=bool(verified),
            checksum=checksum,
        )

        row = entry.to_dict()

        with self._lock:
            self._rotate_if_needed_unlocked()
            with self._jsonl.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            self._cache.append(row)
            if len(self._cache) > 2000:
                self._cache = self._cache[-2000:]

        # sinks (best‑effort)
        self._sink_action(entry)
        self._sink_mission(entry)

        return row

    def get_all_logs(self) -> List[Dict[str, Any]]:
        with self._lock:
            data = self._load_all_unlocked()
        return data

    def get_logs_by_module(self, module_name: str) -> List[Dict[str, Any]]:
        name = (module_name or "").lower()
        return [e for e in self.get_all_logs() if e.get("module", "").lower() == name]

    def get_logs_by_source(self, source_id: str) -> List[Dict[str, Any]]:
        sid = (source_id or "").lower()
        return [e for e in self.get_all_logs() if e.get("source", "").lower() == sid]

    def verify_last_action(self) -> Optional[bool]:
        with self._lock:
            last = self._last_unlocked()
        if last is None:
            return None
        # recompute checksum for last entry
        expected = FounderTraceEntry.make_checksum(
            last["module"], last["action"], last["source"], bool(last["override"]), bool(last["verified_founder"]), last["timestamp"]
        )
        return bool(last.get("verified_founder")) and (expected == last.get("checksum"))

    # ---------------- New helpers ----------------

    def tail(self, n: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            data = self._load_all_unlocked()
        return data[-int(n):]

    def export_json(self) -> List[Dict[str, Any]]:
        with self._lock:
            return self._load_all_unlocked()

    def filter(self, *, module: Optional[str] = None, source: Optional[str] = None, verified_only: bool = False, limit: int = 200) -> List[Dict[str, Any]]:
        data = self.export_json()
        out: List[Dict[str, Any]] = []
        m = (module or "").lower()
        s = (source or "").lower()
        for e in reversed(data):
            if m and e.get("module", "").lower() != m:
                continue
            if s and e.get("source", "").lower() != s:
                continue
            if verified_only and not e.get("verified_founder"):
                continue
            out.append(e)
            if len(out) >= limit:
                break
        return list(reversed(out))

    def verify_integrity(self) -> bool:
        """
        Verify all stored checksums match their fields — detects tampering.
        """
        data = self.export_json()
        for e in data:
            expected = FounderTraceEntry.make_checksum(
                e.get("module", ""), e.get("action", ""), e.get("source", ""),
                bool(e.get("override", False)), bool(e.get("verified_founder", False)), e.get("timestamp", "")
            )
            if expected != e.get("checksum", ""):
                return False
        return True

    # ---------------- Internals ----------------

    def _load_all_unlocked(self) -> List[Dict[str, Any]]:
        # Prefer disk (authoritative), fall back to cache if file missing
        if not self._jsonl.exists():
            return list(self._cache)
        with self._jsonl.open("r", encoding="utf-8") as f:
            rows = [json.loads(r) for r in f if r.strip()]
        return rows

    def _last_unlocked(self) -> Optional[Dict[str, Any]]:
        if self._cache:
            return self._cache[-1]
        if not self._jsonl.exists():
            return None
        try:
            # read last few lines cheaply
            with self._jsonl.open("rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                back = min(4096, size)
                f.seek(-back, os.SEEK_END)
                chunk = f.read().decode("utf-8", errors="ignore")
                lines = [ln for ln in chunk.splitlines() if ln.strip()]
                for ln in reversed(lines):
                    try:
                        return json.loads(ln)
                    except Exception:
                        continue
        except Exception:
            pass
        return None

    def _rotate_if_needed_unlocked(self) -> None:
        try:
            if self._jsonl.exists() and self._jsonl.stat().st_size > self._max_bytes:
                ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
                rotated = self._jsonl.with_name(f"{self._jsonl.stem}.{ts}{self._jsonl.suffix}")
                shutil.copy2(self._jsonl, rotated)
                self._jsonl.unlink(missing_ok=True)
                # keep last N backups
                family = sorted(self._jsonl.parent.glob(f"{self._jsonl.stem}.*{self._jsonl.suffix}"), reverse=True)
                for old in family[self._keep_backups:]:
                    try:
                        old.unlink()
                    except OSError:
                        pass
        except Exception:
            # never break tracing due to rotation issues
            pass

    # ---------------- Sinks ----------------

    def _sink_action(self, e: FounderTraceEntry) -> None:
        if not self._action_logger:
            return
        try:
            self._action_logger.log(
                action_type="FounderTrace",
                user_input=e.action[:160],
                system_decision="FOUNDER" if e.verified_founder else "OTHER",
                module=e.module,
                reason=f"override={e.override}",
                status="Success",
            )
        except Exception:
            pass

    def _sink_mission(self, e: FounderTraceEntry) -> None:
        if not self._mission_log_sink:
            return
        try:
            verdict = "halal" if e.verified_founder else "shubha"
            score = 0.05 if e.verified_founder else 0.35
            self._mission_log_sink({
                "actor_id": e.source if e.source else "unknown",
                "activity": "founder_trace",
                "verdict": verdict,
                "score": score,
                "reasons": [f"module={e.module}", f"override={e.override}"],
                "tags": ["trace", "founder" if e.verified_founder else "other"],
                "payload": e.to_dict(),
            })
        except Exception:
            pass


# ---------------- Minimal self-test ----------------
if __name__ == "__main__":
    ft = FounderTrace()
    ft.log_action("core.init", "boot", source="husnain_ali", override=True)
    ft.log_action("guardian", "blocked_riba_ad", source="system")
    print("last verified:", ft.verify_last_action())
    print("tail:", ft.tail(2))
    print("integrity:", ft.verify_integrity())
