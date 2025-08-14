# core/deen_refresher_hooks.py
# -----------------------------------------------------------------------------
# Links Phase 3.50 (DeenSystemRefresher) with Phase 3.49 (DeenActivityMonitor)
# Provides concrete hooks that operate on the shared monitor instance, safely.
# -----------------------------------------------------------------------------

from __future__ import annotations

from typing import Any, Dict, Tuple

from core.deen_activity_monitor import DeenActivityMonitor
from core.deen_system_refresher import RefresherHooks

# Shared monitor instance (can be imported by API/main as needed)
monitor = DeenActivityMonitor()


def _ok(data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    return True, data


def _fail(msg: str) -> Tuple[bool, Dict[str, Any]]:
    return False, {"error": msg}


def purge_caches() -> Tuple[bool, Dict[str, Any]]:
    """
    Clears debounce and EWMA caches in the monitor.
    """
    try:
        with monitor._lock:  # type: ignore[attr-defined]
            # Debounce signatures + EWMA intensities
            getattr(monitor, "_last_signature_at", {}).clear()
            getattr(monitor, "_ewma_by_actor", {}).clear()
        return _ok({"purged": ["debounce_map", "ewma"]})
    except Exception as e:
        return _fail(f"purge_caches: {type(e).__name__}: {e}")


def shrink_metrics() -> Tuple[bool, Dict[str, Any]]:
    """
    Shrinks stored event windows to free memory (keeps the newest half).
    """
    try:
        removed = 0
        with monitor._lock:  # type: ignore[attr-defined]
            events_by_actor = getattr(monitor, "_events_by_actor", {})
            for actor, q in events_by_actor.items():
                # drop oldest half
                half = len(q) // 2
                for _ in range(half):
                    q.popleft()
                removed += half
        return _ok({"shrunk": "event_windows", "removed_oldest": removed})
    except Exception as e:
        return _fail(f"shrink_metrics: {type(e).__name__}: {e}")


def reload_activity_classifier() -> Tuple[bool, Dict[str, Any]]:
    """
    Reloads monitor's keyword rules (idempotent placeholder).
    You can later swap to a learned classifier here.
    """
    try:
        with monitor._lock:  # type: ignore[attr-defined]
            cls = monitor.classifier.__class__
            monitor.classifier = cls(
                allow=("charity", "zakat", "quran", "hadith", "education", "halal"),
                flag=("music", "idle", "argue", "waste", "boast"),
                deny=("riba", "interest", "gambling", "nudity", "porn", "alcohol"),
            )
        return _ok({"status": "classifier_reloaded"})
    except Exception as e:
        return _fail(f"reload_activity_classifier: {type(e).__name__}: {e}")


def health_check() -> Tuple[bool, Dict[str, Any]]:
    """
    Lightweight snapshot useful before/after maintenance.
    Avoids depending on optional snapshot methods.
    """
    try:
        with monitor._lock:  # type: ignore[attr-defined]
            counts = {}
            for k, v in getattr(monitor, "_counts", {}).items():
                key = getattr(k, "value", str(k))
                counts[key] = int(v)

            events_per_actor = {
                actor: len(q) for actor, q in getattr(monitor, "_events_by_actor", {}).items()
            }
            ewma = {
                actor: round(val, 3) for actor, val in getattr(monitor, "_ewma_by_actor", {}).items()
            }
            debounce_size = len(getattr(monitor, "_last_signature_at", {}))

        return _ok({
            "actors": len(events_per_actor),
            "events_in_windows": sum(events_per_actor.values()),
            "events_per_actor": events_per_actor,
            "verdict_counts": counts,
            "ewma_by_actor": ewma,
            "debounce_cache_size": debounce_size,
        })
    except Exception as e:
        return _fail(f"health_check: {type(e).__name__}: {e}")


# Export hooks object for DeenSystemRefresher
hooks = RefresherHooks(
    purge_caches=purge_caches,
    shrink_metrics=shrink_metrics,
    reload_activity_classifier=reload_activity_classifier,
    health_check=health_check,  # optional extra hook
)
