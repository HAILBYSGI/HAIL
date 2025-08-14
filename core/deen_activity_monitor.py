# Phase 3.49 – deen_activity_monitor.py (Upgraded)
# HAIL OS — Core
# -----------------------------------------------------------------------------
# Responsibilities:
# - Normalize incoming ActivityEvent signals
# - Classify per Islamic constraints (pluggable classifier)
# - Compute risk scores with taqwa sensitivity
# - Detect surges in doubtful/haram activity (EWMA + density heuristic)
# - Debounce duplicate events
# - Publish to subscribers (e.g., deen_guardian_trigger)
# - Maintain rolling metrics and an optional audit log
# - Provide snapshot_metrics() and audit export for API/UI
# - Optional sinks: ActionLogger JSONL, MissionLog mirror
# -----------------------------------------------------------------------------

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Callable, Deque, Dict, Iterable, List, Optional, Tuple, Any
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
import json
import threading
import uuid

try:
    from core.action_logger import ActionLogger
except Exception:  # pragma: no cover
    ActionLogger = None  # type: ignore

# ---------- Domain Types ----------

class Verdict(Enum):
    HALAL = "halal"
    SHUBHA = "shubha"  # doubtful/grey area
    HARAM = "haram"

class ActivityType(Enum):
    CONTENT_VIEW = "content_view"
    CONTENT_POST = "content_post"
    MESSAGE_SEND = "message_send"
    PURCHASE = "purchase"
    LOCATION_VISIT = "location_visit"
    FILE_ACCESS = "file_access"
    APP_USAGE = "app_usage"
    SYSTEM_EVENT = "system_event"
    OTHER = "other"

@dataclass(frozen=True)
class ActivityEvent:
    """
    A normalized activity signal within HAIL OS.
    """
    event_id: str
    actor_id: str
    activity: ActivityType
    timestamp: datetime
    payload: Dict[str, str] = field(default_factory=dict)
    tags: Tuple[str, ...] = field(default_factory=tuple)  # normalized lowercase tags

    @staticmethod
    def new(
        actor_id: str,
        activity: ActivityType,
        payload: Optional[Dict[str, str]] = None,
        tags: Optional[Iterable[str]] = None,
        timestamp: Optional[datetime] = None,
    ) -> "ActivityEvent":
        return ActivityEvent(
            event_id=str(uuid.uuid4()),
            actor_id=actor_id,
            activity=activity,
            timestamp=timestamp or datetime.now(timezone.utc),
            payload=payload or {},
            tags=tuple(sorted({*(t.lower().strip() for t in (tags or []))})),
        )

@dataclass
class Classification:
    verdict: Verdict
    confidence: float  # 0.0 .. 1.0
    reasons: List[str] = field(default_factory=list)

# ---------- Classifier Interfaces ----------

class ActivityClassifier:
    """Strategy interface for classifying activities according to Islamic constraints."""
    def classify(self, event: ActivityEvent) -> Classification:
        raise NotImplementedError

class KeywordRuleClassifier(ActivityClassifier):
    """Lightweight, transparent classifier using allow/flag/deny keyword sets."""
    def __init__(self, allow: Iterable[str] = (), flag: Iterable[str] = (), deny: Iterable[str] = ()):
        self.allow = {w.lower().strip() for w in allow}
        self.flag = {w.lower().strip() for w in flag}
        self.deny = {w.lower().strip() for w in deny}

    def classify(self, event: ActivityEvent) -> Classification:
        text_blobs = [
            event.payload.get("title", ""),
            event.payload.get("text", ""),
            event.payload.get("url", ""),
            event.payload.get("category", ""),
            *list(event.tags),
        ]
        text = " ".join(bl.lower() for bl in text_blobs)

        hits_deny = [w for w in self.deny if w in text]
        if hits_deny:
            return Classification(
                verdict=Verdict.HARAM,
                confidence=min(0.95, 0.5 + 0.1 * len(hits_deny)),
                reasons=[f"Matched deny keywords: {', '.join(sorted(hits_deny))}"],
            )

        hits_flag = [w for w in self.flag if w in text]
        if hits_flag:
            return Classification(
                verdict=Verdict.SHUBHA,
                confidence=min(0.9, 0.4 + 0.08 * len(hits_flag)),
                reasons=[f"Matched flag keywords: {', '.join(sorted(hits_flag))}"],
            )

        hits_allow = [w for w in self.allow if w in text]
        if hits_allow:
            return Classification(
                verdict=Verdict.HALAL,
                confidence=min(0.9, 0.3 + 0.07 * len(hits_allow)),
                reasons=[f"Matched allow keywords: {', '.join(sorted(hits_allow))}"],
            )

        return Classification(
            verdict=Verdict.SHUBHA,
            confidence=0.25,
            reasons=["No rule matched; conservative default."],
        )

# ---------- Monitor Configuration ----------

@dataclass
class MonitorConfig:
    window: timedelta = timedelta(minutes=15)
    max_events_per_actor: int = 2000
    debounce: timedelta = timedelta(seconds=3)
    taqwa_sensitivity: float = 0.6
    shubha_weight: float = 0.5
    haram_weight: float = 1.0
    surge_threshold: float = 2.5
    ewma_alpha: float = 0.15
    keep_audit: bool = True
    max_audit_records: int = 10000

@dataclass
class RiskAssessment:
    score: float
    verdict: Verdict
    reasons: List[str] = field(default_factory=list)

# ---------- DeenActivityMonitor ----------

Subscriber = Callable[[ActivityEvent, Classification, RiskAssessment], None]

class DeenActivityMonitor:
    def __init__(
        self,
        config: Optional[MonitorConfig] = None,
        classifier: Optional[ActivityClassifier] = None,
        *,
        action_logger: Optional["ActionLogger"] = None,
        mission_log_sink: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.cfg = config or MonitorConfig()
        self.classifier = classifier or KeywordRuleClassifier(
            allow=("charity", "zakat", "quran", "hadith", "education", "halal"),
            flag=("music", "idle", "argue", "waste", "boast"),
            deny=("riba", "interest", "gambling", "nudity", "porn", "alcohol"),
        )

        self._subscribers: List[Subscriber] = []
        self._lock = threading.RLock()
        self._events_by_actor: Dict[str, Deque[Tuple[datetime, ActivityEvent]]] = defaultdict(deque)
        self._ewma_by_actor: Dict[str, float] = defaultdict(lambda: 0.0)
        self._last_signature_at: Dict[Tuple[str, str], datetime] = {}
        self._audit: Optional[Deque[Dict]] = deque(maxlen=self.cfg.max_audit_records) if self.cfg.keep_audit else None
        self._counts: Dict[Verdict, int] = defaultdict(int)

        self._logger = action_logger
        self._mission_log_sink = mission_log_sink

    # ---- subscription ----
    def subscribe(self, fn: Subscriber) -> None:
        with self._lock:
            self._subscribers.append(fn)

    def unsubscribe(self, fn: Subscriber) -> None:
        with self._lock:
            self._subscribers = [f for f in self._subscribers if f is not fn]

    # ---- emit ----
    def emit(self, event: ActivityEvent) -> Optional[RiskAssessment]:
        with self._lock:
            if self._debounced(event):
                return None

            self._trim_windows(event.actor_id)
            q = self._events_by_actor[event.actor_id]
            q.append((event.timestamp, event))
            if len(q) > self.cfg.max_events_per_actor:
                q.popleft()

            classification = self.classifier.classify(event)
            assessment = self._assess_risk(event.actor_id, classification)

            self._counts[classification.verdict] += 1
            self._update_ewma(event.actor_id, classification)

            surge_reason = self._check_surge(event.actor_id, classification)
            if surge_reason:
                assessment.score = min(1.0, max(assessment.score, 0.85))
                assessment.reasons.append(surge_reason)
                if assessment.verdict != Verdict.HARAM:
                    assessment.verdict = Verdict.SHUBHA

            if self._audit is not None:
                self._audit.append(self._audit_row(event, classification, assessment))

        # sinks (don’t hold lock)
        self._write_sinks(event, classification, assessment)

        # notify subscribers (don’t hold lock)
        for fn in list(self._subscribers):
            try:
                fn(event, classification, assessment)
            except Exception as e:
                if self._audit is not None:
                    self._audit.append({
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "type": "subscriber_error",
                        "error": repr(e),
                    })

        return assessment

    def emit_batch(self, events: Iterable[ActivityEvent]) -> List[RiskAssessment]:
        out: List[RiskAssessment] = []
        for ev in events:
            ra = self.emit(ev)
            if ra is not None:
                out.append(ra)
        return out

    # ---- risk helpers ----
    def _debounced(self, event: ActivityEvent) -> bool:
        signature = self._signature(event)
        key = (event.actor_id, signature)
        now = event.timestamp
        last = self._last_signature_at.get(key)
        if last and (now - last) <= self.cfg.debounce:
            return True
        self._last_signature_at[key] = now
        return False

    @staticmethod
    def _signature(event: ActivityEvent) -> str:
        payload_keys = ("url", "title", "category", "path", "app", "action")
        core = {"a": event.activity.value,
                "p": {k: event.payload.get(k) for k in payload_keys if k in event.payload},
                "t": event.tags}
        return json.dumps(core, sort_keys=True, ensure_ascii=False)

    def _trim_windows(self, actor_id: str) -> None:
        cutoff = datetime.now(timezone.utc) - self.cfg.window
        q = self._events_by_actor[actor_id]
        while q and q[0][0] < cutoff:
            q.popleft()

    def _assess_risk(self, actor_id: str, c: Classification) -> RiskAssessment:
        if c.verdict == Verdict.HALAL:
            base, weight = 0.05, 0.1
        elif c.verdict == Verdict.SHUBHA:
            base, weight = 0.35, self.cfg.shubha_weight
        else:
            base, weight = 0.75, self.cfg.haram_weight
        score = base + (1.0 - base) * (c.confidence * weight * self.cfg.taqwa_sensitivity)
        score = max(0.0, min(1.0, score))
        reasons = list(c.reasons)
        reasons.append(
            f"Risk score={score:.2f} (verdict={c.verdict.value}, conf={c.confidence:.2f}, taqwa={self.cfg.taqwa_sensitivity:.2f})"
        )
        return RiskAssessment(score=score, verdict=c.verdict, reasons=reasons)

    def _update_ewma(self, actor_id: str, c: Classification) -> None:
        intensity = {Verdict.HALAL: 0.0, Verdict.SHUBHA: 0.6, Verdict.HARAM: 1.0}[c.verdict]
        prev = self._ewma_by_actor[actor_id]
        a = self.cfg.ewma_alpha
        self._ewma_by_actor[actor_id] = (1 - a) * prev + a * intensity

    def _check_surge(self, actor_id: str, c: Classification) -> Optional[str]:
        if c.verdict == Verdict.HALAL:
            return None
        ewma = self._ewma_by_actor[actor_id]
        recent_count = len(self._events_by_actor[actor_id])
        if ewma >= 0.5 and recent_count >= 10:
            return f"Surge detected: EWMA={ewma:.2f} with {recent_count} events in window."
        return None

    def _audit_row(self, event: ActivityEvent, c: Classification, r: RiskAssessment) -> Dict:
        return {
            "ts": event.timestamp.isoformat(),
            "actor": event.actor_id,
            "activity": event.activity.value,
            "payload": event.payload,
            "tags": list(event.tags),
            "classification": {
                "verdict": c.verdict.value,
                "confidence": round(c.confidence, 3),
                "reasons": c.reasons,
            },
            "risk": {
                "score": round(r.score, 3),
                "verdict": r.verdict.value,
                "reasons": r.reasons,
            },
        }

    # ---- sinks ----
    def _write_sinks(self, ev: ActivityEvent, c: Classification, r: RiskAssessment) -> None:
        if self._logger:
            try:
                self._logger.log(
                    action_type="Activity",
                    decision=("APPROVED" if c.verdict == Verdict.HALAL else "WARN" if c.verdict == Verdict.SHUBHA else "DENIED"),
                    module="deen_activity_monitor",
                    status="Success",
                    user_input=ev.payload.get("title") or ev.payload.get("text"),
                    actor_id=ev.actor_id,
                    source=ev.payload.get("source") or "monitor",
                    reason="; ".join(c.reasons)[:300],
                    context={"activity": ev.activity.value, "tags": list(ev.tags), "risk_score": r.score},
                    meta={"verdict": c.verdict.value, "confidence": c.confidence},
                )
            except Exception:
                pass
        if self._mission_log_sink:
            try:
                verdict = {"halal": "halal", "shubha": "shubha", "haram": "haram"}[c.verdict.value]
                self._mission_log_sink({
                    "actor_id": ev.actor_id,
                    "activity": ev.activity.value,
                    "verdict": verdict,
                    "score": float(r.score),
                    "reasons": list(c.reasons),
                    "tags": list(ev.tags),
                    "payload": self._audit_row(ev, c, r),
                })
            except Exception:
                pass

    # ---- API helpers for server/UI ----
    def snapshot_metrics(self) -> Dict[str, Any]:
        """Fast metrics snapshot for dashboards."""
        with self._lock:
            verdict_counts = {k.value if isinstance(k, Verdict) else str(k): int(v) for k, v in self._counts.items()}
            events_per_actor = {actor: len(q) for actor, q in self._events_by_actor.items()}
            total_events = sum(events_per_actor.values())
            ewma = {actor: round(val, 3) for actor, val in self._ewma_by_actor.items()}
            debounce_size = len(self._last_signature_at)
        return {
            "actors": len(events_per_actor),
            "total_events_in_windows": total_events,
            "events_per_actor": events_per_actor,
            "verdict_counts": verdict_counts,
            "ewma_by_actor": ewma,
            "debounce_cache_size": debounce_size,
        }

    def export_audit_json(self) -> str:
        """Return audit log as a JSON string (safe for API)."""
        with self._lock:
            if self._audit is None:
                return "[]"
            return json.dumps(list(self._audit), ensure_ascii=False)

    def clear(self) -> None:
        """Reset rolling state (not classifier/config)."""
        with self._lock:
            self._events_by_actor.clear()
            self._ewma_by_actor.clear()
            self._last_signature_at.clear()
            self._counts.clear()
            if self._audit is not None:
                self._audit.clear()

# ---------- Example hook ----------

def guardian_hook(event: ActivityEvent, c: Classification, r: RiskAssessment) -> None:
    # Example subscriber placeholder
    pass

# ---------- Minimal usage example ----------

if __name__ == "__main__":
    monitor = DeenActivityMonitor(action_logger=ActionLogger(also_print=True) if ActionLogger else None)
    monitor.subscribe(guardian_hook)
    sample = [
        ActivityEvent.new("user123", ActivityType.CONTENT_VIEW,
                          payload={"title": "How to calculate zakat", "url": "https://example.org/zakat"},
                          tags=["islamic", "education"]),
        ActivityEvent.new("user123", ActivityType.CONTENT_VIEW,
                          payload={"title": "sports highlights", "category": "entertainment"},
                          tags=["idle"]),
        ActivityEvent.new("user123", ActivityType.CONTENT_VIEW,
                          payload={"title": "High APR credit card offers", "url": "https://ads.example/interest"},
                          tags=["finance", "riba"]),
    ]
    for ev in sample:
        ra = monitor.emit(ev)
        if ra:
            print(f"{ev.activity.value} -> {ra.verdict.value} | score={ra.score:.2f} | reasons={'; '.join(ra.reasons)}")
    print("Metrics:", json.dumps(monitor.snapshot_metrics(), indent=2))
