# core/deen_system_refresher.py
# -----------------------------------------------------------------------------
# Phase 3.50 – DeenSystemRefresher (Upgraded)
# - Lightweight maintenance passes for Deen Core
# - Safe hook execution with timeouts
# - Pre/Post health snapshots (if hook provided)
# - Optional sinks: ActionLogger + Mission Log
# - Idempotent start/stop; safe timer teardown
# -----------------------------------------------------------------------------

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Callable, Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta, timezone
import threading
import uuid
import json
import hashlib
import secrets

# ---------- Config & Data Models ----------

@dataclass
class RefresherConfig:
    interval: timedelta = timedelta(minutes=10)  # auto-refresh interval
    task_timeout: timedelta = timedelta(seconds=2)
    audit_window: int = 2000
    enable_auto: bool = False

@dataclass
class TaskResult:
    name: str
    ok: bool
    duration_ms: int
    details: Dict[str, Any] = field(default_factory=dict)

@dataclass
class RefreshReport:
    run_id: str
    started_at: datetime
    finished_at: datetime
    results: List[TaskResult] = field(default_factory=list)
    pre_health: Optional[Dict[str, Any]] = None
    post_health: Optional[Dict[str, Any]] = None
    summary: Optional[Dict[str, Any]] = None  # quick pass/fail counts etc.

    def to_json(self) -> str:
        def enc(o):
            if isinstance(o, datetime):
                return o.isoformat()
            if isinstance(o, TaskResult):
                return asdict(o)
            return o
        return json.dumps(asdict(self), default=enc, ensure_ascii=False, indent=2)

# Hook type aliases (inject real implementations in production)
PurgeHook = Callable[[], Tuple[bool, Dict[str, Any]]]
RotateKeyHook = Callable[[], Tuple[bool, Dict[str, Any]]]
ReloadClassifierHook = Callable[[], Tuple[bool, Dict[str, Any]]]
HealthCheckHook = Callable[[], Tuple[bool, Dict[str, Any]]]
TaqwaReadHook = Callable[[], Tuple[bool, Dict[str, Any]]]
TaqwaBroadcastHook = Callable[[float], Tuple[bool, Dict[str, Any]]]
GuardianWarmHook = Callable[[], Tuple[bool, Dict[str, Any]]]
MetricShrinkHook = Callable[[], Tuple[bool, Dict[str, Any]]]
CustomTaskHook = Callable[[], Tuple[bool, Dict[str, Any]]]

@dataclass
class RefresherHooks:
    purge_caches: Optional[PurgeHook] = None
    rotate_ephemeral_keys: Optional[RotateKeyHook] = None
    reload_activity_classifier: Optional[ReloadClassifierHook] = None
    health_check_subsystems: Optional[HealthCheckHook] = None
    read_taqwa_level: Optional[TaqwaReadHook] = None
    broadcast_taqwa_level: Optional[TaqwaBroadcastHook] = None
    warm_guardian_paths: Optional[GuardianWarmHook] = None
    shrink_metrics: Optional[MetricShrinkHook] = None
    custom_tasks: List[Tuple[str, CustomTaskHook]] = field(default_factory=list)

# ---------- Optional sinks (no hard dependency) ----------

try:
    from core.action_logger import ActionLogger  # type: ignore
except Exception:  # pragma: no cover
    ActionLogger = None  # type: ignore

# ---------- Core Refresher ----------

class DeenSystemRefresher:
    def __init__(
        self,
        config: Optional[RefresherConfig] = None,
        hooks: Optional[RefresherHooks] = None,
        *,
        action_logger: Optional["ActionLogger"] = None,
        mission_log_sink: Optional[Callable[[Dict[str, Any]], None]] = None,  # lambda payload: mission_log.append(...)
    ):
        self.cfg = config or RefresherConfig()
        self.hooks = hooks or RefresherHooks()
        self._audit: List[Dict] = []
        self._lock = threading.RLock()
        self._timer: Optional[threading.Timer] = None
        self._running_auto = False
        self.log = action_logger
        self.mission_log_sink = mission_log_sink

    def run_once(self) -> RefreshReport:
        with self._lock:
            run_id = str(uuid.uuid4())
            started = datetime.now(timezone.utc)

        results: List[TaskResult] = []

        # Optional pre-health snapshot
        pre_health = self._maybe_health_snapshot()

        def run_task(name: str, fn: Optional[Callable[[], Tuple[bool, Dict[str, Any]]]]) -> TaskResult:
            t0 = datetime.now(timezone.utc)
            if fn is None:
                return TaskResult(name=name, ok=True, duration_ms=0, details={"skip": "no-hook"})

            done = threading.Event()
            holder: Dict[str, Any] = {}

            def worker():
                try:
                    ok, details = fn()
                    holder["ok"] = bool(ok)
                    holder["details"] = details or {}
                except Exception as e:
                    holder["ok"] = False
                    holder["details"] = {"error": repr(e)}
                finally:
                    done.set()

            th = threading.Thread(target=worker, daemon=True)
            th.start()
            done.wait(timeout=self.cfg.task_timeout.total_seconds())
            if not done.is_set():
                ok, details = False, {"timeout": f">{self.cfg.task_timeout.total_seconds()}s"}
            else:
                ok = bool(holder.get("ok", False))
                details = dict(holder.get("details", {}))
            t1 = datetime.now(timezone.utc)
            return TaskResult(name=name, ok=ok, duration_ms=int((t1 - t0).total_seconds() * 1000), details=details)

        # Core maintenance tasks
        results.append(run_task("purge_caches", self.hooks.purge_caches))
        results.append(run_task("shrink_metrics", self.hooks.shrink_metrics))
        results.append(run_task("reload_activity_classifier", self.hooks.reload_activity_classifier))
        results.append(run_task("rotate_ephemeral_keys", self.hooks.rotate_ephemeral_keys))
        results.append(run_task("health_check_subsystems", self.hooks.health_check_subsystems))

        # Taqwa sensitivity
        new_taqwa: Optional[float] = None
        r_read = run_task("read_taqwa_level", self.hooks.read_taqwa_level)
        results.append(r_read)
        if r_read.ok and isinstance(r_read.details, dict) and "taqwa" in r_read.details:
            try:
                new_taqwa = float(r_read.details["taqwa"])
            except Exception:
                new_taqwa = None
        if new_taqwa is not None and self.hooks.broadcast_taqwa_level:
            results.append(run_task("broadcast_taqwa_level", lambda: self.hooks.broadcast_taqwa_level(new_taqwa)))

        results.append(run_task("warm_guardian_paths", self.hooks.warm_guardian_paths))

        # Custom hooks
        for name, fn in self.hooks.custom_tasks:
            results.append(run_task(f"custom:{name}", fn))

        finished = datetime.now(timezone.utc)
        # Optional post-health snapshot
        post_health = self._maybe_health_snapshot()

        # Summary
        ok_count = sum(1 for r in results if r.ok)
        fail_count = sum(1 for r in results if not r.ok)
        summary = {
            "ok": ok_count,
            "fail": fail_count,
            "duration_ms_total": int((finished - started).total_seconds() * 1000),
        }

        report = RefreshReport(
            run_id=run_id,
            started_at=started,
            finished_at=finished,
            results=results,
            pre_health=pre_health,
            post_health=post_health,
            summary=summary,
        )

        # Audit buffer
        with self._lock:
            self._audit.append(json.loads(report.to_json()))
            if len(self._audit) > self.cfg.audit_window:
                self._audit = self._audit[-self.cfg.audit_window:]

        # Sinks
        self._sinks(report)

        return report

    # --------- Auto scheduler ---------

    def start(self) -> None:
        with self._lock:
            if self._running_auto:
                return
            self._running_auto = True
        if self.cfg.enable_auto:
            self._schedule_next()

    def stop(self) -> None:
        with self._lock:
            self._running_auto = False
            if self._timer:
                try:
                    self._timer.cancel()
                finally:
                    self._timer = None

    def audit_json(self) -> str:
        with self._lock:
            return json.dumps(self._audit, ensure_ascii=False, indent=2)

    # --------- Internals ---------

    def _schedule_next(self):
        with self._lock:
            if not self._running_auto:
                return
            delay = max(1.0, self.cfg.interval.total_seconds())
            self._timer = threading.Timer(delay, self._auto_tick)
            self._timer.daemon = True
            self._timer.start()

    def _auto_tick(self):
        try:
            self.run_once()
        finally:
            self._schedule_next()

    def _maybe_health_snapshot(self) -> Optional[Dict[str, Any]]:
        fn = self.hooks.health_check_subsystems
        if not fn:
            return None
        try:
            ok, details = fn()
            return {"ok": bool(ok), "details": details or {}}
        except Exception as e:
            return {"ok": False, "details": {"error": repr(e)}}

    def _sinks(self, report: RefreshReport) -> None:
        # Action Logger (optional)
        if self.log:
            try:
                self.log.log(
                    action_type="RefresherRun",
                    decision="APPROVED" if report.summary and report.summary.get("fail", 0) == 0 else "WARN",
                    module="deen_system_refresher",
                    status="Success",
                    reason=f"{report.summary['ok']} ok / {report.summary['fail']} fail",
                    context={"run_id": report.run_id},
                    meta={"duration_ms": report.summary["duration_ms_total"] if report.summary else None},
                )
            except Exception:
                pass

        # Mission Log (optional)
        if self.mission_log_sink:
            try:
                failed = report.summary.get("fail", 0) if report.summary else 0
                verdict = "halal" if failed == 0 else "shubha"
                score = 0.05 if failed == 0 else 0.4
                payload = json.loads(report.to_json())
                self.mission_log_sink({
                    "actor_id": "system:refresher",
                    "activity": "maintenance_run",
                    "verdict": verdict,
                    "score": score,
                    "reasons": [f"Refresher completed with {report.summary['ok']} ok / {failed} fail"],
                    "tags": ["maintenance", "refresher", "system"],
                    "payload": payload,
                })
            except Exception:
                pass


# ---------- Demo Hooks (kept for local testing) ----------

def _demo_purge() -> Tuple[bool, Dict[str, Any]]:
    return True, {"purged": "classifier_cache, debounce_map, ewma"}

def _demo_shrink() -> Tuple[bool, Dict[str, Any]]:
    return True, {"shrunk": "windows:-20%"}

def _demo_reload_classifier() -> Tuple[bool, Dict[str, Any]]:
    revision = hashlib.sha256(secrets.token_bytes(8)).hexdigest()[:8]
    return True, {"rule_revision": revision}

def _demo_rotate_keys() -> Tuple[bool, Dict[str, Any]]:
    key_id = hashlib.sha256(secrets.token_bytes(16)).hexdigest()[:12]
    return True, {"ephemeral_key_id": key_id}

def _demo_health() -> Tuple[bool, Dict[str, Any]]:
    return True, {"guardian": "warm", "activity_monitor": "alive"}

def _demo_read_taqwa() -> Tuple[bool, Dict[str, Any]]:
    return True, {"taqwa": "0.62", "source": "taqwa_sensitivity_controller"}

def _demo_broadcast_taqwa(level: float) -> Tuple[bool, Dict[str, Any]]:
    return True, {"broadcast_to": "activity_monitor, guardian_trigger", "level": f"{level:.2f}"}

def _demo_warm() -> Tuple[bool, Dict[str, Any]]:
    return True, {"warm_paths": "guardian/escalate, guardian/notify"}

# ---------- Minimal usage example ----------

if __name__ == "__main__":
    cfg = RefresherConfig(enable_auto=False, interval=timedelta(minutes=5))
    hooks = RefresherHooks(
        purge_caches=_demo_purge,
        shrink_metrics=_demo_shrink,
        reload_activity_classifier=_demo_reload_classifier,
        rotate_ephemeral_keys=_demo_rotate_keys,
        health_check_subsystems=_demo_health,
        read_taqwa_level=_demo_read_taqwa,
        broadcast_taqwa_level=_demo_broadcast_taqwa,
        warm_guardian_paths=_demo_warm,
    )
    refresher = DeenSystemRefresher(cfg, hooks)
    report = refresher.run_once()
    print(report.to_json())
