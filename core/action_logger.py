# core/action_logger.py
# Part of HAIL Phase 3 – AI Ethics, Command & Security Logic
# Structured JSONL logs, UTC timestamps, size rotation, and helper APIs.

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _utc_now_iso() -> str:
    # RFC 3339/ISO 8601 with Z
    return datetime.now(timezone.utc).isoformat()


@dataclass
class LogEntry:
    ts: str                      # ISO 8601 UTC timestamp
    action_type: str             # e.g., "Command", "Event", "Decision"
    decision: str                # e.g., "APPROVED", "DENIED", "BLOCKED", "INFO"
    module: str                  # producing module, e.g., "shariah_guard"
    status: str                  # e.g., "Success", "Failure"
    user_input: Optional[str] = None
    actor_id: Optional[str] = None
    source: Optional[str] = None
    reason: Optional[str] = None
    reasons: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


class ActionLogger:
    """
    JSONL logger for HAIL. Each log line is a single JSON object.
    - File auto-creates parent directories
    - Light size-based rotation to avoid runaway growth
    """

    def __init__(
        self,
        log_path: str = "hail_logs/action_log.jsonl",
        max_bytes: int = 2 * 1024 * 1024,   # ~2MB per file
        keep_backups: int = 5,
        also_print: bool = False,
    ) -> None:
        self.log_path = log_path
        self.max_bytes = max_bytes
        self.keep_backups = keep_backups
        self.also_print = also_print

        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)

    # -------- public API

    def log(
        self,
        *,
        action_type: str,
        decision: str,
        module: str,
        status: str,
        user_input: Optional[str] = None,
        actor_id: Optional[str] = None,
        source: Optional[str] = None,
        reason: Optional[str] = None,
        reasons: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        entry = LogEntry(
            ts=_utc_now_iso(),
            action_type=action_type,
            decision=decision,
            module=module,
            status=status,
            user_input=user_input,
            actor_id=actor_id,
            source=source,
            reason=reason,
            reasons=reasons or [],
            context=context or {},
            meta=meta or {},
        )
        self._write(entry)
        return {"status": "LOGGED", "ts": entry.ts, "path": self.log_path}

    def log_decision(self, decision_dict: Dict[str, Any], *, module: str, action_type: str = "Decision") -> Dict[str, Any]:
        """
        Convenience for logging results from ActionBlocker or similar components.
        Expects keys like: block, reason, reasons, code, meta
        """
        decision = "BLOCKED" if decision_dict.get("block") else "APPROVED"
        return self.log(
            action_type=action_type,
            decision=decision,
            module=module,
            status="Success",
            reason=decision_dict.get("reason"),
            reasons=decision_dict.get("reasons", []),
            context={},  # caller can pass context if needed
            meta={"code": decision_dict.get("code"), **decision_dict.get("meta", {})},
        )

    def log_exception(self, *, module: str, err: Exception, where: str = "", context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self.log(
            action_type="Exception",
            decision="ERROR",
            module=module,
            status="Failure",
            reason=f"{type(err).__name__}: {err}",
            context=(context or {}) | {"where": where},
        )

    # -------- private

    def _write(self, entry: LogEntry) -> None:
        self._rotate_if_needed()
        line = entry.to_json()
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        if self.also_print:
            print(line)

    def _rotate_if_needed(self) -> None:
        try:
            if os.path.exists(self.log_path) and os.path.getsize(self.log_path) >= self.max_bytes:
                ts = time.strftime("%Y%m%d-%H%M%S")
                base, ext = os.path.splitext(self.log_path)
                rotated = f"{base}.{ts}{ext or '.jsonl'}"
                os.replace(self.log_path, rotated)
                self._cleanup_backups(base)
        except Exception as e:
            # never block main flow on rotation
            if self.also_print:
                print(f'{{"ts":"{_utc_now_iso()}","action_type":"Logger","decision":"WARN","module":"action_logger","status":"RotationError","reason":"{e}"}}')

    def _cleanup_backups(self, base: str) -> None:
        # keep most recent N backups
        folder = os.path.dirname(self.log_path) or "."
        prefix = os.path.basename(base) + "."
        files = sorted(
            [f for f in os.listdir(folder) if f.startswith(prefix)],
            reverse=True
        )
        for f in files[self.keep_backups:]:
            try:
                os.remove(os.path.join(folder, f))
            except OSError:
                pass


# Example usage
if __name__ == "__main__":
    log = ActionLogger(also_print=True)
    log.log(
        action_type="Command",
        decision="APPROVED",
        module="shariah_guard",
        status="Success",
        user_input="Send charity request to Ummah Center",
        reason="Halal intent and validated source",
        reasons=["Intent classified halal", "No interest/riba detected"],
        actor_id="husnain",
        source="cli",
        context={"intent": "charity_request"},
    )
