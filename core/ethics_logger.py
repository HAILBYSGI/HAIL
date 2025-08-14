# core/ethics_logger.py
# HAIL — EthicsLogger (Upgraded)
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Optional, Sequence


# ----- helpers -----
def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class EthicsEvent:
    timestamp: str
    event_type: str
    system_module: str
    description: str
    severity: str = "medium"  # low | medium | high | critical
    tags: List[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["tags"] = list(self.tags or [])
        return d


class EthicsLogger:
    """
    Dual writer: human‑readable .txt + structured .jsonl
    - Thread‑safe append
    - File rotation by size
    - Backwards compatible get_logs(filter_by)
    """

    VALID_SEVERITY = {"low", "medium", "high", "critical"}

    def __init__(
        self,
        log_dir: str = "hail/logs",
        *,
        text_name: str = "ethics_log.txt",
        json_name: str = "ethics_log.jsonl",
        max_bytes: int = 2_000_000,   # ~2 MB
        keep_backups: int = 5,
    ) -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.text_path = self.log_dir / text_name
        self.jsonl_path = self.log_dir / json_name

        self.max_bytes = int(max_bytes)
        self.keep_backups = int(keep_backups)
        self._lock = RLock()

        # Optional sinks (best‑effort)
        try:
            from core.action_logger import ActionLogger  # type: ignore
            self._action_logger = ActionLogger()
        except Exception:
            self._action_logger = None

        self._mission_log_sink = None  # set with set_mission_log_sink(fn)

    # -------------------- Public API --------------------

    def log_event(
        self,
        event_type: str,
        description: str,
        system_module: str,
        severity: str = "medium",
        tags: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        sev = (severity or "medium").lower().strip()
        if sev not in self.VALID_SEVERITY:
            sev = "medium"

        entry = EthicsEvent(
            timestamp=_utc_iso(),
            event_type=str(event_type or "event").strip(),
            system_module=str(system_module or "core").strip(),
            description=str(description or "").strip(),
            severity=sev,
            tags=list(tags or []),
        )

        with self._lock:
            self._rotate_if_needed_unlocked(self.text_path)
            self._rotate_if_needed_unlocked(self.jsonl_path)

            # write text
            with self.text_path.open("a", encoding="utf-8") as f_txt:
                f_txt.write(self._format_text(entry) + "\n")

            # write jsonl
            with self.jsonl_path.open("a", encoding="utf-8") as f_js:
                f_js.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")

        # Sinks
        if self._action_logger:
            try:
                self._action_logger.log(
                    action_type="EthicsEvent",
                    user_input=entry.description[:160],
                    system_decision=entry.event_type.upper(),
                    module=entry.system_module,
                    reason=f"severity={entry.severity} tags={','.join(entry.tags or [])}",
                    status="Success",
                )
            except Exception:
                pass

        if self._mission_log_sink:
            try:
                verdict = "halal" if entry.severity in {"low", "medium"} else "shubha"
                score = 0.1 if entry.severity in {"low", "medium"} else 0.35
                self._mission_log_sink({
                    "actor_id": f"module:{entry.system_module}",
                    "activity": "ethics_event",
                    "verdict": verdict,
                    "score": score,
                    "reasons": [entry.description[:120]],
                    "tags": ["ethics", entry.severity] + list(entry.tags or []),
                    "payload": entry.to_dict(),
                })
            except Exception:
                pass

        return entry.to_dict()

    def get_logs(self, filter_by: Optional[str] = None) -> List[str]:
        """
        Backwards‑compatible: returns lines from the text log.
        If filter_by provided, only lines containing the substring are returned.
        """
        if not self.text_path.exists():
            return []
        with self.text_path.open("r", encoding="utf-8") as f:
            lines = f.readlines()
        if filter_by:
            return [ln for ln in lines if filter_by in ln]
        return lines

    # -------------------- Convenience (new) --------------------

    def tail(self, n: int = 100) -> List[Dict[str, Any]]:
        """Tail last n structured events (from JSONL)."""
        if not self.jsonl_path.exists():
            return []
        with self.jsonl_path.open("r", encoding="utf-8") as f:
            rows = f.readlines()[-int(n):]
        out = []
        for r in rows:
            try:
                out.append(json.loads(r))
            except Exception:
                continue
        return out

    def export_json(self) -> List[Dict[str, Any]]:
        """Load entire JSONL as a list of dicts (for API/UI)."""
        if not self.jsonl_path.exists():
            return []
        with self.jsonl_path.open("r", encoding="utf-8") as f:
            return [json.loads(r) for r in f if r.strip()]

    def filter(self, *, severity: Optional[str] = None, tag: Optional[str] = None, module: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        """Structured filter from JSONL."""
        data = self.export_json()
        res: List[Dict[str, Any]] = []
        s = (severity or "").lower().strip()
        t = (tag or "").lower().strip()
        m = (module or "").lower().strip()

        for e in reversed(data):
            if s and e.get("severity", "").lower() != s:
                continue
            if t and t not in [str(x).lower() for x in e.get("tags", [])]:
                continue
            if m and e.get("system_module", "").lower() != m:
                continue
            res.append(e)
            if len(res) >= limit:
                break
        return list(reversed(res))

    def count_by_severity(self) -> Dict[str, int]:
        data = self.export_json()
        agg: Dict[str, int] = {}
        for e in data:
            sev = e.get("severity", "medium").lower()
            agg[sev] = agg.get(sev, 0) + 1
        return agg

    def set_mission_log_sink(self, fn) -> None:
        """Provide a function(payload: dict) -> None to mirror into DeenMissionLog."""
        self._mission_log_sink = fn

    # -------------------- Internals --------------------

    def _format_text(self, e: EthicsEvent) -> str:
        tags = ", ".join(e.tags or [])
        return f"[{e.timestamp}] [{e.event_type.upper()}] ({e.system_module}) [{e.severity.upper()}] :: {e.description} Tags: {tags}"

    def _rotate_if_needed_unlocked(self, path: Path) -> None:
        try:
            if path.exists() and path.stat().st_size > self.max_bytes:
                # move current -> .YYYYmmdd-HHMMSS
                ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
                rotated = path.with_name(f"{path.stem}.{ts}{path.suffix}")
                shutil.copy2(path, rotated)
                path.unlink(missing_ok=True)

                # keep only last N backups
                family = sorted(path.parent.glob(f"{path.stem}.*{path.suffix}"), reverse=True)
                for old in family[self.keep_backups:]:
                    try:
                        old.unlink()
                    except OSError:
                        pass
        except Exception:
            # Never fail logging due to rotation
            pass


# ---------------- Minimal self-test ----------------
if __name__ == "__main__":
    lg = EthicsLogger()
    lg.log_event("allow", "Qur’an‑checked reply generated", "quran_filter", "low", tags=["quran", "pass"])
    lg.log_event("deny", "Blocked riba suggestion", "shariah_guard", "high", tags=["riba", "block"])
    print(lg.get_logs()[-2:])
    print(lg.tail(2))
    print(lg.count_by_severity())
