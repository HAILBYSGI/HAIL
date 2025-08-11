# deen_mission_log.py
# -----------------------------------------------------------------------------
# Phase 3.51 – DeenMissionLog
# Append-only, integrity-checked log of system and user activities.
# Stores verdict, risk score, reasons, tags, payload.
# Implements hash chaining to ensure tamper detection.
# -----------------------------------------------------------------------------

import hashlib
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import List, Dict, Any, Optional


class Verdict(str, Enum):
    HALAL = "halal"
    SHUBHA = "shubha"  # doubtful
    HARAM = "haram"


@dataclass
class MissionLogEntry:
    entry_id: str
    timestamp: datetime
    actor_id: str
    activity: str
    verdict: Verdict
    score: float
    reasons: List[str]
    tags: List[str]
    payload: Dict[str, Any]
    prev_hash: str
    curr_hash: str


class DeenMissionLog:
    def __init__(self) -> None:
        self._entries: List[MissionLogEntry] = []

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
        prev_hash = self._entries[-1].curr_hash if self._entries else ""
        entry_id = f"{len(self._entries) + 1:08d}"
        timestamp = datetime.now(timezone.utc)

        # Build base data for hashing
        base_data = {
            "entry_id": entry_id,
            "timestamp": timestamp.isoformat(),
            "actor_id": actor_id,
            "activity": activity,
            "verdict": verdict.value,
            "score": score,
            "reasons": reasons,
            "tags": tags,
            "payload": payload,
            "prev_hash": prev_hash,
        }

        # Hash chain
        curr_hash = hashlib.sha256(json.dumps(base_data, sort_keys=True).encode()).hexdigest()

        entry = MissionLogEntry(
            entry_id=entry_id,
            timestamp=timestamp,
            actor_id=actor_id,
            activity=activity,
            verdict=verdict,
            score=score,
            reasons=reasons,
            tags=tags,
            payload=payload,
            prev_hash=prev_hash,
            curr_hash=curr_hash,
        )
        self._entries.append(entry)
        return entry

    def export_json(self) -> str:
        """
        Export all entries as JSON string.
        """
        return json.dumps([asdict(e) for e in self._entries], default=str, indent=2)

    def verify_integrity(self) -> bool:
        """
        Verify the hash chain for tamper detection.
        Returns True if the entire chain is valid.
        """
        for i, entry in enumerate(self._entries):
            prev_hash = self._entries[i - 1].curr_hash if i > 0 else ""
            base_data = {
                "entry_id": entry.entry_id,
                "timestamp": entry.timestamp.isoformat(),
                "actor_id": entry.actor_id,
                "activity": entry.activity,
                "verdict": entry.verdict.value,
                "score": entry.score,
                "reasons": entry.reasons,
                "tags": entry.tags,
                "payload": entry.payload,
                "prev_hash": prev_hash,
            }
            expected_hash = hashlib.sha256(json.dumps(base_data, sort_keys=True).encode()).hexdigest()
            if entry.curr_hash != expected_hash:
                return False
        return True

    def get_entries(self) -> List[MissionLogEntry]:
        """
        Return all entries.
        """
        return list(self._entries)


# ---------------- Quick self-test ----------------
if __name__ == "__main__":
    log = DeenMissionLog()
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
