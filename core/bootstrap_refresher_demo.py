# core/bootstrap_refresher_demo.py
# Utility to run DeenSystemRefresher once (or on a loop) with optional sample events.
# Usage examples:
#   python -m core.bootstrap_refresher_demo --emit-samples
#   python -m core.bootstrap_refresher_demo --interval-min 5 --loop
#   python -m core.bootstrap_refresher_demo --json

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import timedelta

from core.deen_system_refresher import DeenSystemRefresher, RefresherConfig
from core.deen_refresher_hooks import hooks, monitor  # monitor is provided by hooks
from core.deen_activity_monitor import ActivityEvent, ActivityType


def emit_sample_events(actor_id: str = "user123") -> None:
    """Emit a couple of events so refresher has something to maintain."""
    monitor.emit(ActivityEvent.new(
        actor_id=actor_id,
        activity=ActivityType.CONTENT_VIEW,
        payload={"title": "How to calculate zakat"},
        tags=["islamic", "education"]
    ))
    monitor.emit(ActivityEvent.new(
        actor_id=actor_id,
        activity=ActivityType.CONTENT_VIEW,
        payload={"title": "High APR credit card offers", "url": "https://ads.example/interest"},
        tags=["finance", "riba"]
    ))


def run_once(interval_min: float, json_out: bool) -> int:
    refresher = DeenSystemRefresher(
        config=RefresherConfig(enable_auto=False, interval=timedelta(minutes=interval_min)),
        hooks=hooks
    )
    report = refresher.run_once()

    if json_out:
        # If your RefresherReport has to_json(), prefer that; else build minimal JSON.
        try:
            print(report.to_json())
        except Exception:
            print(json.dumps({
                "run_id": getattr(report, "run_id", None),
                "started_at": getattr(report, "started_at", None).isoformat() if getattr(report, "started_at", None) else None,
                "finished_at": getattr(report, "finished_at", None).isoformat() if getattr(report, "finished_at", None) else None,
                "results": [getattr(r, "__dict__", str(r)) for r in getattr(report, "results", [])],
            }, ensure_ascii=False))
    else:
        total = len(getattr(report, "results", []))
        passed = sum(1 for r in getattr(report, "results", []) if getattr(r, "ok", False))
        failed = total - passed
        print(f"✅ Refresher finished: {passed}/{total} tasks ok, {failed} failed")
        print(f"   run_id: {getattr(report, 'run_id', 'n/a')}")
        print(f"   time : {getattr(report, 'started_at', 'n/a')} → {getattr(report, 'finished_at', 'n/a')}")

    # Optional: show a quick metrics snapshot
    try:
        snap = monitor.snapshot_metrics()
        if json_out:
            print(json.dumps({"monitor_metrics": snap}, ensure_ascii=False))
        else:
            print("— Monitor metrics snapshot —")
            print(json.dumps(snap, indent=2, ensure_ascii=False))
    except Exception:
        # monitor may not expose snapshot_metrics() in older versions
        pass

    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Run DeenSystemRefresher with optional sample events.")
    p.add_argument("--emit-samples", action="store_true", help="Emit a couple of sample events into the monitor first.")
    p.add_argument("--actor", default="user123", help="Actor id for sample events (default: user123).")
    p.add_argument("--interval-min", type=float, default=5.0, help="Maintenance interval minutes to record in config (default: 5).")
    p.add_argument("--loop", action="store_true", help="Run repeatedly (infinite loop) using the given interval.")
    p.add_argument("--sleep-min", type=float, default=None, help="When --loop, how many minutes to sleep between runs (default: interval-min).")
    p.add_argument("--json", action="store_true", help="Print JSON output instead of human-readable.")
    args = p.parse_args(argv)

    if args.emit_samples:
        emit_sample_events(actor_id=args.actor)

    if not args.loop:
        return run_once(args.interval_min, json_out=args.json)

    # loop mode
    sleep_min = args.sleep_min if args.sleep_min is not None else args.interval_min
    print(f"⏳ Loop mode: running refresher every {sleep_min} minute(s). Press Ctrl+C to stop.")
    try:
        while True:
            rc = run_once(args.interval_min, json_out=args.json)
            time.sleep(max(1.0, sleep_min * 60.0))
            if rc != 0:
                # keep looping even if non-zero once, but you can break if you prefer strict
                pass
    except KeyboardInterrupt:
        print("\n🛑 Stopped by user.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
