# Phase 3.50 – deen_system_refresher.py
# HAIL OS — Core Maintenance & Hygiene
# -----------------------------------------------------------------------------
# Responsibilities:
# - Lightweight maintenance passes to keep Deen Core healthy
# - Purge stale caches and shrink in-memory windows
# - Reload pluggable classifiers (e.g., from rule snapshots)
# - Rotate ephemeral keys used by non-critical subsystems
# - Run health checks on dependent subsystems
# - Read taqwa sensitivity and broadcast updates
# - Warm guardian paths after config drift
# - Append audit reports for observability
# -----------------------------------------------------------------------------

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple
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
    details: Dict[str, str] = field(default_factory=dict)

@dataclass
class RefreshReport:
    run_id: str
    started_at: datetime
    finished_at: datetime
    results: List[TaskResult] = field(default_factory=list)

    def to_json(self) -> str:
        def enc(o):
            if isinstance(o, datetime):
                return o.isoformat()
            return o
        return json.dumps({
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "results": [r.__dict__ for r in self.results]
        }, default=enc, ensure_ascii=False, indent=2)

# Hook type aliases (inject real implementations in production)
PurgeHook = Callable[[], Tuple[bool, Dict[str, str]]]
RotateKeyHook = Callable[[], Tuple[bool, Dict[str, str]]]
ReloadClassifierHook = Callable[[], Tuple[bool, Dict[str, str]]]
HealthCheckHook = Callable[[], Tuple[bool, Dict[str, str]]]
TaqwaReadHook = Callable[[], Tuple[bool, Dict[str, str]]]
TaqwaBroadcastHook = Callable[[float], Tuple[bool, Dict[str, str]]]
GuardianWarmHook = Callable[[], Tuple[bool, Dict[str, str]]]
MetricShrinkHook = Callable[[], Tuple[bool, Dict[str, str]]]
CustomTaskHook = Callable[[], Tuple[bool, Dict[str, str]]]

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

# ---------- Core Refresher ----------

class DeenSystemRefresher:
    def __init__(self, config: Optional[RefresherConfig] = None, hooks: Optional[RefresherHooks] = None):
        self.cfg = config or RefresherConfig()
        self.hooks = hooks or RefresherHooks()
        self._audit: List[Dict] = []
        self._lock = threading.RLock()
        self._timer: Optional[threading.Timer] = None
        self._stopped = True

    def run_once(self) -> RefreshReport:
        with self._lock:
            run_id = str(uuid.uuid4())
            started = datetime.now(timezone.utc)
        results: List[TaskResult] = []

        def run_task(name: str, fn: Callable[[], Tuple[bool, Dict[str, str]]]):
            t0 = datetime.now(timezone.utc)
            ok, details = False, {}
            if fn is None:
                return TaskResult(name=name, ok=True, duration_ms=0, details={"skip": "no-hook"})
            done = threading.Event()
            result_holder: Dict[str, object] = {}

            def worker():
                try:
                    r_ok, r_details = fn()
                    result_holder["ok"] = bool(r_ok)
                    result_holder["details"] = r_details or {}
                except Exception as e:
                    result_holder["ok"] = False
                    result_holder["details"] = {"error": repr(e)}
                finally:
                    done.set()

            th = threading.Thread(target=worker, daemon=True)
            th.start()
            done.wait(timeout=self.cfg.task_timeout.total_seconds())
            if not done.is_set():
                ok, details = False, {"timeout": f">{self.cfg.task_timeout.total_seconds()}s"}
            else:
                ok = bool(result_holder.get("ok", False))
                details = dict(result_holder.get("details", {}))
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
        if r_read.ok and "taqwa" in r_read.details:
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
        report = RefreshReport(run_id=run_id, started_at=started, finished_at=finished, results=results)

        with self._lock:
            self._audit.append(json.loads(report.to_json()))
            if len(self._audit) > self.cfg.audit_window:
                self._audit = self._audit[-self.cfg.audit_window:]

        return report

    def start(self) -> None:
        with self._lock:
            self._stopped = False
        if self.cfg.enable_auto:
            self._schedule_next()

    def stop(self) -> None:
        with self._lock:
            self._stopped = True
            if self._timer:
                self._timer.cancel()
                self._timer = None

    def audit_json(self) -> str:
        with self._lock:
            return json.dumps(self._audit, ensure_ascii=False, indent=2)

    def _schedule_next(self):
        with self._lock:
            if self._stopped:
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

# ---------- Demo Hooks (replace in production) ----------

def _demo_purge() -> Tuple[bool, Dict[str, str]]:
    return True, {"purged": "classifier_cache, debounce_map, ewma"}

def _demo_shrink() -> Tuple[bool, Dict[str, str]]:
    return True, {"shrunk": "windows:-20%"}

def _demo_reload_classifier() -> Tuple[bool, Dict[str, str]]:
    revision = hashlib.sha256(secrets.token_bytes(8)).hexdigest()[:8]
    return True, {"rule_revision": revision}

def _demo_rotate_keys() -> Tuple[bool, Dict[str, str]]:
    key_id = hashlib.sha256(secrets.token_bytes(16)).hexdigest()[:12]
    return True, {"ephemeral_key_id": key_id}

def _demo_health() -> Tuple[bool, Dict[str, str]]:
    return True, {"guardian": "warm", "activity_monitor": "alive"}

def _demo_read_taqwa() -> Tuple[bool, Dict[str, str]]:
    return True, {"taqwa": "0.62", "source": "taqwa_sensitivity_controller"}

def _demo_broadcast_taqwa(level: float) -> Tuple[bool, Dict[str, str]]:
    return True, {"broadcast_to": "activity_monitor, guardian_trigger", "level": f"{level:.2f}"}

def _demo_warm() -> Tuple[bool, Dict[str, str]]:
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
