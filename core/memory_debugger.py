# core/memory_debugger.py
# HAIL — MemoryDebugger (Upgraded, backward compatible)
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Dict, List, Iterable, Optional, Iterator, Any
import json
import uuid


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class MemEvent:
    id: str
    ts: str
    level: str
    event_type: str
    description: str
    tags: List[str]
    context: Dict[str, Any]


class MemoryDebugger:
    """
    Backward-compatible memory/phase debug logger with filters, spans and exports.

    Existing methods kept:
      - log(event_type, description)
      - get_recent_logs(limit=10)
      - clear_logs()
      - export_logs()           # text export (original style)

    New:
      - log(level=..., tags=[...], context={...})
      - export_json()
      - find(level=None, tag=None, text=None, limit=None)
      - count_by_level()
      - since(seconds=..)
      - start_span(name, ...), end_span(span_id, ...)
      - span(name, ...)  # context manager
      - configure(max_events=...)
    """

    LEVELS = ("debug", "info", "warn", "error")

    def __init__(self, *, max_events: int = 5000, mission_log_sink: Optional[callable] = None) -> None:
        self._lock = RLock()
        self._logs: List[MemEvent] = []
        self._max = int(max_events)
        self._spans: Dict[str, Dict[str, Any]] = {}  # span_id -> {name, start_ts, tags, context}
        self._mission_log_sink = mission_log_sink

        # Optional sink: ActionLogger (best-effort)
        try:
            from core.action_logger import ActionLogger  # type: ignore
            self._action_logger = ActionLogger()
        except Exception:  # pragma: no cover
            self._action_logger = None

    # ---------------- Backward-compatible API ----------------

    def log(self, event_type: str, description: str,
            *, level: str = "info", tags: Optional[Iterable[str]] = None,
            context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        level = level.lower()
        if level not in self.LEVELS:
            level = "info"

        ev = MemEvent(
            id=str(uuid.uuid4())[:12],
            ts=_utcnow_iso(),
            level=level,
            event_type=str(event_type),
            description=str(description),
            tags=sorted({*(t.lower().strip() for t in (tags or []))}),
            context=dict(context or {}),
        )
        with self._lock:
            self._logs.append(ev)
            if len(self._logs) > self._max:
                # trim oldest ~10% to reduce churn
                cut = max(1, self._max // 10)
                self._logs = self._logs[cut:]

        self._sink_action(ev)
        self._sink_mission(ev, is_span=False)
        return asdict(ev)

    def get_recent_logs(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._lock:
            return [asdict(e) for e in self._logs[-int(limit):]]

    def clear_logs(self) -> None:
        with self._lock:
            self._logs.clear()
            self._spans.clear()

    def export_logs(self) -> str:
        # text export (original style)
        with self._lock:
            lines = [
                f"[{e.ts}] {e.level.upper()} {e.event_type}: {e.description}"
                + (f" Tags: {', '.join(e.tags)}" if e.tags else "")
                for e in self._logs
            ]
        return "\n".join(lines)

    # ---------------- New exports & queries ----------------

    def export_json(self) -> str:
        with self._lock:
            return json.dumps([asdict(e) for e in self._logs], ensure_ascii=False, indent=2)

    def count_by_level(self) -> Dict[str, int]:
        with self._lock:
            out = {lvl: 0 for lvl in self.LEVELS}
            for e in self._logs:
                out[e.level] = out.get(e.level, 0) + 1
            return out

    def since(self, *, seconds: int) -> List[Dict[str, Any]]:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=int(seconds))
        with self._lock:
            out = [asdict(e) for e in self._logs if _parse_iso(e.ts) >= cutoff]
        return out

    def find(self, *, level: Optional[str] = None, tag: Optional[str] = None,
             text: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        tag = (tag or "").lower().strip()
        lvl = (level or "").lower().strip()
        txt = (text or "").lower()
        res: List[MemEvent] = []

        with self._lock:
            for e in reversed(self._logs):
                if lvl and e.level != lvl:
                    continue
                if tag and tag not in e.tags:
                    continue
                if txt and (txt not in e.description.lower() and txt not in e.event_type.lower()):
                    continue
                res.append(e)
                if limit and len(res) >= limit:
                    break

        return [asdict(e) for e in reversed(res)]

    # ---------------- Spans / timers ----------------

    def start_span(self, name: str, *, tags: Optional[Iterable[str]] = None,
                   context: Optional[Dict[str, Any]] = None) -> str:
        span_id = str(uuid.uuid4())[:12]
        with self._lock:
            self._spans[span_id] = {
                "name": name,
                "start_ts": datetime.now(timezone.utc),
                "tags": sorted({*(t.lower().strip() for t in (tags or []))}),
                "context": dict(context or {}),
            }
        # also log start
        self.log("SPAN_START", f"{name} started", level="debug", tags=["span", *(tags or [])], context=context)
        return span_id

    def end_span(self, span_id: str, *, outcome: str = "ok", notes: Optional[str] = None) -> Optional[Dict[str, Any]]:
        with self._lock:
            span = self._spans.pop(span_id, None)
        if not span:
            return None

        dur = (datetime.now(timezone.utc) - span["start_ts"]).total_seconds()
        entry = self.log(
            "SPAN_END",
            f"{span['name']} finished ({outcome}) in {dur:.3f}s" + (f" — {notes}" if notes else ""),
            level="debug",
            tags=["span", outcome],
            context={"duration_s": dur, **span["context"]},
        )
        # Mission sink for spans
        self._sink_mission_span(span["name"], dur, outcome, tags=span["tags"])
        return entry

    def span(self, name: str, *, tags: Optional[Iterable[str]] = None,
             context: Optional[Dict[str, Any]] = None):
        """Context manager for timing blocks:  with dbg.span('index:phase2'): ..."""
        dbg = self
        class _Span:
            def __enter__(self_inner):
                self_inner._id = dbg.start_span(name, tags=tags, context=context)
                return self_inner
            def __exit__(self_inner, exc_type, exc, tb):
                outcome = "error" if exc else "ok"
                note = repr(exc) if exc else None
                dbg.end_span(self_inner._id, outcome=outcome, notes=note)
                # Do not suppress exceptions
                return False
        return _Span()

    # ---------------- Config ----------------

    def configure(self, *, max_events: Optional[int] = None) -> None:
        if max_events is not None and max_events > 100:
            with self._lock:
                self._max = int(max_events)

    # ---------------- Sinks ----------------

    def _sink_action(self, ev: MemEvent) -> None:
        if not self._action_logger:
            return
        try:
            self._action_logger.log(
                action_type=f"Memory:{ev.event_type}",
                user_input=(ev.description[:180] or ""),
                system_decision=ev.level.upper(),
                module="memory_debugger",
                reason=",".join(ev.tags) if ev.tags else "",
                status="Logged",
            )
        except Exception:
            pass

    def _sink_mission(self, ev: MemEvent, *, is_span: bool) -> None:
        if not callable(self._mission_log_sink):
            return
        try:
            # Map levels to verdict & nominal score
            verdict = "halal" if ev.level in {"debug", "info"} else "shubha"
            score = 0.1 if ev.level in {"debug", "info"} else 0.35
            self._mission_log_sink({
                "actor_id": "system:memory",
                "activity": "memory_event",
                "verdict": verdict,
                "score": score,
                "reasons": [ev.event_type, ev.description[:120]],
                "tags": ["memory", ev.level, *ev.tags],
                "payload": asdict(ev),
            })
        except Exception:
            pass

    def _sink_mission_span(self, name: str, duration_s: float, outcome: str, *, tags: List[str]) -> None:
        if not callable(self._mission_log_sink):
            return
        try:
            score = 0.15 if outcome == "ok" else 0.4
            verdict = "halal" if outcome == "ok" else "shubha"
            self._mission_log_sink({
                "actor_id": "system:memory",
                "activity": "memory_span",
                "verdict": verdict,
                "score": score,
                "reasons": [f"span:{name}", f"duration:{duration_s:.3f}s", f"outcome:{outcome}"],
                "tags": ["memory", "span", outcome, *tags],
                "payload": {"name": name, "duration_s": duration_s, "outcome": outcome, "tags": tags},
            })
        except Exception:
            pass


# ------------- Helpers -------------

def _parse_iso(s: str) -> datetime:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)


# ---------------- Minimal self-test ----------------
if __name__ == "__main__":
    dbg = MemoryDebugger(max_events=20)
    dbg.log("INDEX", "Phase 2.3 indexed successfully.", tags=["phase2", "index"])
    dbg.log("FILTER", "Qur'an filter applied to message.", level="debug")
    with dbg.span("reindex:blueprint", tags=["phase2"]):
        dbg.log("READ", "Loaded blueprint v1", tags=["phase2"])
    print("--- TEXT ---")
    print(dbg.export_logs())
    print("--- JSON ---")
    print(dbg.export_json())
    print("counts:", dbg.count_by_level())
    print("find warn:", dbg.find(level="warn"))
