# deen_refresher_hooks.py
# -----------------------------------------------------------------------------
# Links Phase 3.50 (DeenSystemRefresher) with Phase 3.49 (DeenActivityMonitor)
# by providing real hooks that operate on the monitor instance.
# -----------------------------------------------------------------------------

from .deen_activity_monitor import DeenActivityMonitor
from .deen_system_refresher import RefresherHooks

# Create a shared monitor instance (or import from where you run your app)
monitor = DeenActivityMonitor()

def purge_caches():
    """Clears debounce and EWMA caches in the monitor."""
    monitor._last_signature_at.clear()
    monitor._ewma_by_actor.clear()
    return True, {"purged": "debounce_map, ewma"}

def shrink_metrics():
    """Shrinks stored event windows by half to free memory."""
    for actor, q in monitor._events_by_actor.items():
        half = len(q) // 2
        for _ in range(half):
            q.popleft()
    return True, {"shrunk": "event_windows:-50%"}

def reload_activity_classifier():
    """Reloads monitor's keyword rules (basic placeholder)."""
    monitor.classifier = monitor.classifier.__class__(
        allow=("charity", "zakat", "quran", "hadith", "education", "halal"),
        flag=("music", "idle", "argue", "waste", "boast"),
        deny=("riba", "interest", "gambling", "nudity", "porn", "alcohol")
    )
    return True, {"status": "classifier reloaded"}

# Export hooks object for DeenSystemRefresher
hooks = RefresherHooks(
    purge_caches=purge_caches,
    shrink_metrics=shrink_metrics,
    reload_activity_classifier=reload_activity_classifier
)
