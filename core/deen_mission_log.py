# core/deen_mission_log.py
# -----------------------------------------------------------------------------
# Phase 3.51 – DeenMissionLog (Upgraded)
# - Append-only, integrity-checked mission log (hash chain)
# - Thread-safe; optional file persistence with atomic writes + rotation
# - Structured dataclasses; quick query helpers for the dashboard
# - Backwards compatible API: append(), export_json(), verify_integrity(), get_entries()
# -----------------------------------------------------------------------------

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from threading import RLock
from typing import List, Dict, Any, Optional, Iterable


class Verdict(str, Enum):
    HALAL = "halal"
    SHUBHA = "shubha"  # doubtful
    HARAM = "haram"


@dataclass
class MissionLogEntry:
    entry_id: str
    timestamp: str                 # stored as ISO string for portability
    actor_id: str
    activity: str
    verdict: Verdict
    score: float
    reasons: List[str]
    tags: List[str]
    payload: Dict[str, Any]
    prev_hash: str
    curr_hash: str


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DeenMissionLog:
    """
    Append-only mission log with integrity chain.
    Persistence (optional):
      - If log_path is provided, entries are saved on each append using atomic writes.
      - Rotates when exceeding max_size_bytes (keeps a few backups).
    """

    def __init__(
        self,
        *,
        log_path: Optional[str] = "hail_logs/mission_log.json",
        max_size_bytes: int = 2_000_000,  # ~2MB
        keep_backups: int = 5,
        chain_salt: Optional[str] = None,  # extra salt in hash chain (defense-in-depth)
    ) -> None:
        self._entries: List[MissionLogEntry] = []
        self._lock = RLock()

        self._path: Optional[Path] = Path(log_path) if log_path else None
        self._max_size = int(max_size_bytes)
        self._keep_backups = int(keep_backups)
        self._salt = chain_salt or ""

        if self._path:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            # load existing if present
            if self._path.exists():
                try:
                    raw = json.loads(self._path.read_text(encoding="utf-8"))
                    for item in raw:
                        self._entries.append(self._from_dict(item))
                except Exception:
                    # if corrupt, start fresh (chain will reflect reset)
                    self._entries = []
            else:
                self._atomic_write([])

    # ------------------------ Public API ------------------------

    def append(
        self,
        actor_id: str,
        activity: str,
        verdict: Verdict,
        score: float,
        reasons: List[str],
        tags: List[str],
        payload: Dict[str, Any],
    ) -> MissionLogEntry:
        """
        Append a new log entry with integrity chaining.
        """
        with self._lock:
            prev_hash = self._entries[-1].curr_hash if self._entries else ""
            entry_id = f"{len(self._entries) + 1:08d}"
            timestamp = _utc_iso()

            base = self._base_for_hash(
                entry_id=entry_id,
                timestamp=timestamp,
                actor_id=actor_id,
                activity=activity,
                verdict=verdict.value,
                score=score,
                reasons=reasons,
                tags=tags,
                payload=payload,
                prev_hash=prev_hash,
            )
            curr_hash = self._digest(base)

            entry = MissionLogEntry(
                entry_id=entry_id,
                timestamp=timestamp,
                actor_id=actor_id,
                activity=activity,
                verdict=verdict,
                score=float(score),
                reasons=list(reasons),
                tags=list(tags),
                payload=dict(payload),
                prev_hash=prev_hash,
                curr_hash=curr_hash,
            )
            self._entries.append(entry)

            # persist
            if self._path:
                self._persist()

            return entry

    def export_json(self) -> str:
        """
        Export all entries as JSON string (pretty).
        """
        with self._lock:
            return json.dumps([asdict(e) for e in self._entries], ensure_ascii=False, indent=2)

    def verify_integrity(self) -> bool:
        """
        Verify the hash chain for tamper detection.
        Returns True if the entire chain is valid.
        """
        with self._lock:
            prev = ""
            for e in self._entries:
                base = self._base_for_hash(
                    entry_id=e.entry_id,
                    timestamp=e.timestamp,
                    actor_id=e.actor_id,
                    activity=e.activity,
                    verdict=e.verdict.value,
                    score=e.score,
                    reasons=e.reasons,
                    tags=e.tags,
                    payload=e.payload,
                    prev_hash=prev,
                )
                if self._digest(base) != e.curr_hash:
                    return False
                prev = e.curr_hash
            return True

    def get_entries(self) -> List[MissionLogEntry]:
        with self._lock:
            return list(self._entries)

    # --------- Convenience for dashboards (non-breaking helpers) ----------

    def tail(self, n: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            return [asdict(e) for e in self._entries[-int(n):]]

    def find_by_actor(self, actor_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            res = [asdict(e) for e in reversed(self._entries) if e.actor_id == actor_id]
            return list(reversed(res[:limit]))

    def find_by_tag(self, tag: str, limit: int = 100) -> List[Dict[str, Any]]:
        t = (tag or "").lower().strip()
        with self._lock:
            res = [asdict(e) for e in reversed(self._entries) if t in [x.lower() for x in e.tags]]
            return list(reversed(res[:limit]))

    def clear(self) -> None:
        with self._lock:
            self._entries = []
            if self._path:
                self._atomic_write([])

    # ------------------------ Internals ------------------------

    def _persist(self) -> None:
        # rotate if large
        try:
            if self._path and self._path.exists() and self._path.stat().st_size > self._max_size:
                self._rotate()
        except Exception:
            pass

        if self._path:
            data = [asdict(e) for e in self._entries]
            self._atomic_write(data)

    def _atomic_write(self, data: List[Dict[str, Any]]) -> None:
        assert self._path is not None
        tmp_fd, tmp_path = tempfile.mkstemp(prefix="mission_", suffix=".json", dir=str(self._path.parent))
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as tmp:
                json.dump(data, tmp, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self._path)
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass

    def _rotate(self) -> None:
        assert self._path is not None
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        backup = self._path.parent / f"mission_log.{ts}.json"
        try:
            shutil.copy2(self._path, backup)
            # keep only latest N backups
            backups = sorted(self._path.parent.glob("mission_log.*.json"), reverse=True)
            for old in backups[self._keep_backups:]:
                try:
                    old.unlink()
                except OSError:
                    pass
        except Exception:
            pass

    def _base_for_hash(
        self,
        *,
        entry_id: str,
        timestamp: str,
        actor_id: str,
        activity: str,
        verdict: str,
        score: float,
        reasons: Iterable[str],
        tags: Iterable[str],
        payload: Dict[str, Any],
        prev_hash: str,
    ) -> Dict[str, Any]:
        return {
            "entry_id": entry_id,
            "timestamp": timestamp,
            "actor_id": actor_id,
            "activity": activity,
            "verdict": verdict,
            "score": float(score),
            "reasons": list(reasons),
            "tags": list(tags),
            "payload": payload,
            "prev_hash": prev_hash,
            "salt": self._salt,  # not secret, but strengthens uniqueness
        }

    def _digest(self, base: Dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(base, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

    def _from_dict(self, d: Dict[str, Any]) -> MissionLogEntry:
        # tolerate older dumps where timestamp may be datetime string already
        return MissionLogEntry(
            entry_id=str(d["entry_id"]),
            timestamp=str(d["timestamp"]),
            actor_id=str(d["actor_id"]),
            activity=str(d["activity"]),
            verdict=Verdict(str(d["verdict"])),
            score=float(d.get("score", 0.0)),
            reasons=list(d.get("reasons", [])),
            tags=list(d.get("tags", [])),
            payload=dict(d.get("payload", {})),
            prev_hash=str(d.get("prev_hash", "")),
            curr_hash=str(d.get("curr_hash", "")),
        )


# ---------------- Quick self-test ----------------
if __name__ == "__main__":
    log = DeenMissionLog(log_path=None)  # in-memory
    log.append(
        actor_id="user123",
        activity="content_view",
        verdict=Verdict.HALAL,
        score=0.0,
        reasons=["educational content"],
        tags=["islamic", "education"],
        payload={"title": "How to calculate zakat"},
    )
    log.append(
        actor_id="user456",
        activity="content_view",
        verdict=Verdict.HARAM,
        score=1.0,
        reasons=["contains riba-related content"],
        tags=["finance", "riba"],
        payload={"title": "High APR credit card offers"},
    )
    print(log.export_json())
    print("Integrity OK:", log.verify_integrity())
