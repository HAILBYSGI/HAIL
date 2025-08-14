# core/main.py
# HAIL OS Core API (Chat + Deen monitor + OpenAI backend + simple data storage)

import os, re, json, time
from datetime import timedelta, datetime
from typing import Dict, List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# -------- HAIL core (your modules) ----------
from core.deen_activity_monitor import DeenActivityMonitor, ActivityEvent, ActivityType
from core.deen_system_refresher import DeenSystemRefresher, RefresherConfig
from core.deen_mission_log import DeenMissionLog, Verdict

# -------- Chat store (Step A) ----------
from core.chat_store import append_message, load_all as load_chat_history

# -------- OpenAI ----------
from openai import OpenAI

# ========== ENV & PATHS ==========
load_dotenv()
OPENAI_KEY  = os.getenv("OPENAI_API_KEY", "")
MODEL_NAME  = os.getenv("HAIL_OPENAI_MODEL", "gpt-4o-mini")
DEBUG       = os.getenv("HAIL_DEBUG", "false").lower() == "true"

# access gate flags (used by /health and /beta_signup)
REQUIRE_EMAIL = os.getenv("HAIL_REQUIRE_EMAIL", "true").lower() == "true"
GMAIL_ONLY    = os.getenv("HAIL_BETA_GMAIL_ONLY", "false").lower() == "true"

FRONTEND_DIR = "frontend"

# Persist beta signups next to chat history
BETA_PATH = os.path.join("hail_data", "beta_signups.json")
os.makedirs(os.path.dirname(BETA_PATH), exist_ok=True)
if not os.path.exists(BETA_PATH):
    with open(BETA_PATH, "w", encoding="utf-8") as f:
        json.dump([], f)

# ========== APP & CORS ==========
app = FastAPI(title="HAIL OS Core", version="0.4.0")

if os.path.isdir(FRONTEND_DIR):
    app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR), name="frontend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # dev only; restrict in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========== SINGLETONS ==========
monitor = DeenActivityMonitor()
mission_log = DeenMissionLog()
refresher = DeenSystemRefresher(
    config=RefresherConfig(enable_auto=False, interval=timedelta(minutes=10))
)
client: Optional[OpenAI] = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

# ========== MONITOR -> MISSION LOG BRIDGE ==========
def _mission_log_subscriber(ev: ActivityEvent, c, r):
    payload: Dict = {
        "event_id": ev.event_id,
        "payload": ev.payload,
        "classification": {
            "verdict": c.verdict.value,
            "confidence": round(c.confidence, 3),
            "reasons": list(c.reasons),
        },
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

# ========== SCHEMAS ==========
class EmitEventIn(BaseModel):
    actor_id: str
    activity: ActivityType
    payload: Dict[str, str] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)

class AskRequest(BaseModel):
    question: str
    actor_id: Optional[str] = "user_web"
    lang: Optional[str] = None

class AskResponse(BaseModel):
    answer: str
    verdict: Optional[str] = None
    score: Optional[float] = None

class BetaSignup(BaseModel):
    email: str

# ========== PAGES ==========
@app.get("/")
def serve_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

@app.get("/gate")
def serve_gate():
    return FileResponse(os.path.join(FRONTEND_DIR, "gate.html"))

@app.get("/app")
def serve_app():
    return FileResponse(os.path.join(FRONTEND_DIR, "app.html"))

# ========== HEALTH / METRICS / LOGS ==========
@app.get("/health")
def health():
    return {
        "status": "ok",
        "model": f"openai:{MODEL_NAME}" if OPENAI_KEY else "unconfigured",
        "now": datetime.utcnow().isoformat(),
        "require_email": REQUIRE_EMAIL,
        "gmail_only": GMAIL_ONLY,
    }

@app.get("/metrics")
def metrics():
    try:
        with monitor._lock:  # type: ignore[attr-defined]
            counts = {}
            for k, v in getattr(monitor, "_counts", {}).items():
                key = getattr(k, "value", str(k))
                counts[key] = int(v)

            events_per_actor = {
                actor: len(q) for actor, q in getattr(monitor, "_events_by_actor", {}).items()
            }
            total_events = sum(events_per_actor.values())

            ewma = {
                actor: round(val, 3) for actor, val in getattr(monitor, "_ewma_by_actor", {}).items()
            }
            debounce_size = len(getattr(monitor, "_last_signature_at", {}))

        return {
            "actors": len(events_per_actor),
            "total_events_in_windows": total_events,
            "events_per_actor": events_per_actor,
            "verdict_counts": counts,
            "ewma_by_actor": ewma,
            "debounce_cache_size": debounce_size,
        }
    except Exception as e:
        return {"error": repr(e)}

@app.get("/logs")
def logs():
    return {"entries": mission_log.export_json()}

# ========== EVENTS ==========
@app.post("/emit_event")
def emit_event(data: EmitEventIn):
    ev = ActivityEvent.new(
        actor_id=data.actor_id,
        activity=data.activity,
        payload=data.payload,
        tags=data.tags,
    )
    assessment = monitor.emit(ev)
    if assessment is None:
        return {"event_id": ev.event_id, "status": "debounced"}
    return {
        "event_id": ev.event_id,
        "verdict": assessment.verdict.value,
        "score": round(assessment.score, 3),
        "reasons": assessment.reasons,
    }

# ========== BETA SIGNUP (strict + dedupe) ==========
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

@app.post("/beta_signup")
def beta_signup(payload: BetaSignup):
    email = (payload.email or "").strip().lower()

    if not EMAIL_RE.match(email):
        return {"ok": False, "message": "Please enter a valid email address."}
    if GMAIL_ONLY and not email.endswith("@gmail.com"):
        return {"ok": False, "message": "Gmail address required for beta access."}

    # load current list
    try:
        with open(BETA_PATH, "r", encoding="utf-8") as f:
            arr = json.load(f)
    except Exception:
        arr = []

    if any((x.get("email") or "").lower() == email for x in arr):
        return {"ok": True, "message": "You’re already on the list."}

    arr.append({"email": email, "ts": datetime.utcnow().isoformat()})
    with open(BETA_PATH, "w", encoding="utf-8") as f:
        json.dump(arr, f, ensure_ascii=False, indent=2)

    return {"ok": True, "message": "Thanks! Email saved. Redirecting…"}

# ========== CHAT HISTORY ==========
@app.get("/chat_history")
def chat_history():
    return {"items": load_chat_history()}

# ========== CHAT PROMPT ==========
BANNER = (
    "You are HAIL, a Deen-aligned assistant. Answer helpfully like ChatGPT, "
    "but never assist anything that violates Qur’an & Sunnah. If something is doubtful, "
    "give a gentle caution and suggest a permissible alternative. Keep tone kind and concise."
)

# ========== CHAT ==========
@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    text = (req.question or "")
    lo = text.lower()
    tags: List[str] = []
    if any(t in lo for t in ["riba", "interest"]): tags += ["finance", "riba"]
    if "zakat" in lo: tags += ["islamic", "zakat"]
    if any(t in lo for t in ["dua", "supplication"]): tags += ["dua"]
    if any(t in lo for t in ["quran", "hadith"]): tags += ["islamic", "education"]

    # log the user message
    append_message(req.actor_id or "user_web", "user", text)

    # run monitor
    ev = ActivityEvent.new(
        actor_id=req.actor_id or "user_web",
        activity=ActivityType.MESSAGE_SEND,
        payload={"text": text},
        tags=tags,
    )
    assessment = monitor.emit(ev)

    # no model configured
    if not client:
        verdict = "debounced" if assessment is None else assessment.verdict.value
        score = 0.0 if assessment is None else float(round(assessment.score, 3))
        ans = "Backend not configured with an AI key. (Contact admin)"
        append_message(req.actor_id or "user_web", "assistant", ans, verdict, score)
        return AskResponse(answer=f"{ans} (verdict: {verdict}, score: {score})",
                           verdict=verdict, score=score)

    # AI call
    messages = [
        {"role": "system", "content": BANNER},
        {"role": "user", "content": text},
    ]

    try:
        rsp = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=0.5,
        )
        ai_text = (rsp.choices[0].message.content or "").strip()
    except Exception as e:
        if DEBUG: print("OpenAI error:", repr(e))
        ai_text = "Sorry—backend error while contacting the AI."

    # Shari’ah override
    if assessment and getattr(assessment, "verdict", None) and assessment.verdict.value == "haram":
        ai_text = ("I can’t assist with that request as it appears impermissible (haram). "
                   "If you want, describe the goal and I’ll suggest a halal alternative.")

    # Save & return
    verdict_out = "debounced" if assessment is None else assessment.verdict.value
    score_out = 0.0 if assessment is None else float(round(assessment.score, 3))
    append_message(req.actor_id or "user_web", "assistant", ai_text, verdict_out, score_out)

    return AskResponse(answer=ai_text, verdict=verdict_out, score=score_out)
