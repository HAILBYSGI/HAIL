# core/main.py
# Minimal local API to run HAIL OS Core (Phases 3.49–3.51)

from datetime import timedelta
from typing import Dict, List

from fastapi import FastAPI
from pydantic import BaseModel, Field

# --- Phases ---
from core.deen_activity_monitor import DeenActivityMonitor, ActivityEvent, ActivityType
from core.deen_system_refresher import DeenSystemRefresher, RefresherConfig
from core.deen_mission_log import DeenMissionLog, Verdict

app = FastAPI(title="HAIL OS Core", version="0.1.0")

# --- Singletons for this process ---
monitor = DeenActivityMonitor()
mission_log = DeenMissionLog()
refresher = DeenSystemRefresher(config=RefresherConfig(enable_auto=False, interval=timedelta(minutes=10)))

# --- Bridge: monitor -> mission log (no extra file needed) ---
def _mission_log_subscriber(ev: ActivityEvent, c, r):
    payload: Dict = {
        "event_id": ev.event_id,
        "payload": ev.payload,
        "classification": {"verdict": c.verdict.value, "confidence": round(c.confidence, 3), "reasons": list(c.reasons)},
        "risk": {"score": round(r.score, 3), "reasons": list(r.reasons)},
        "tags": list(ev.tags),
    }
    mission_log.append(
        actor_id=ev.actor_id,
        activity=ev.activity.value,
        verdict=Verdict(c.verdict.value),
        score=float(r.score),
        reasons=list(r.reasons),
        tags=list(ev.tags),
        payload=payload,
    )

monitor.subscribe(_mission_log_subscriber)

# --- Schemas ---
class EmitEventIn(BaseModel):
    actor_id: str
    activity: ActivityType
    payload: Dict[str, str] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)

# --- Routes ---
@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/emit_event")
def emit_event(data: EmitEventIn):
    ev = ActivityEvent.new(actor_id=data.actor_id, activity=data.activity, payload=data.payload, tags=data.tags)
    assessment = monitor.emit(ev)
    if assessment is None:
        return {"event_id": ev.event_id, "status": "debounced"}
    return {
        "event_id": ev.event_id,
        "verdict": assessment.verdict.value,
        "score": round(assessment.score, 3),
        "reasons": assessment.reasons,
    }

@app.get("/metrics")
def metrics():
    return monitor.snapshot_metrics()

@app.post("/refresh")
def run_refresh():
    report = refresher.run_once()

    # Log refresher run summary into mission log (simple in-file bridge)
    total = len(report.results)
    passed = sum(1 for r in report.results if r.ok)
    failed = total - passed
    v = Verdict.HALAL if failed == 0 else Verdict.SHUBHA
    mission_log.append(
        actor_id="system:refresher",
        activity="maintenance_run",
        verdict=v,
        score=0.05 if failed == 0 else 0.4,
        reasons=[f"Refresher completed: {passed}/{total} tasks ok"],
        tags=["maintenance", "refresher", "system"],
        payload={
            "run_id": report.run_id,
            "started_at": report.started_at.isoformat(),
            "finished_at": report.finished_at.isoformat(),
            "results": [r.__dict__ for r in report.results],
        },
    )
    return {"run_id": report.run_id, "passed": passed, "failed": failed}

@app.get("/logs")
def logs():
    # Return plain JSON string saved by mission log
    return {"entries": mission_log.export_json()}
