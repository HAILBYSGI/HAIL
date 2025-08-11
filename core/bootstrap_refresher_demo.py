# core/bootstrap_refresher_demo.py
from datetime import timedelta

from core.deen_system_refresher import DeenSystemRefresher, RefresherConfig
from core.deen_refresher_hooks import hooks, monitor  # monitor lives inside hooks
from core.deen_activity_monitor import ActivityEvent, ActivityType

if __name__ == "__main__":
    # 1) (Optional) Emit a few events into the monitor so there is something to shrink/purge
    monitor.emit(ActivityEvent.new(
        actor_id="user123",
        activity=ActivityType.CONTENT_VIEW,
        payload={"title": "How to calculate zakat"},
        tags=["islamic", "education"]
    ))
    monitor.emit(ActivityEvent.new(
        actor_id="user123",
        activity=ActivityType.CONTENT_VIEW,
        payload={"title": "High APR credit card offers", "url": "https://ads.example/interest"},
        tags=["finance", "riba"]
    ))

    # 2) Create refresher with our linked hooks
    refresher = DeenSystemRefresher(
        config=RefresherConfig(enable_auto=False, interval=timedelta(minutes=5)),
        hooks=hooks
    )

    # 3) Run a single maintenance cycle (purge/shrink/reload)
    report = refresher.run_once()
    print(report.to_json())

    # 4) (Optional) Check current monitor metrics after maintenance
    print(monitor.snapshot_metrics())
