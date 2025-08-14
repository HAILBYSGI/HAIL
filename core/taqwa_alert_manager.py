# core/taqwa_alert_manager.py
# Phase 3 — Deen Signals & Guardrails
# Purpose: Raise/track "taqwa" alerts from across HAIL (ethics, guardian, monitor).
# Backwards compatible with DeenGuardianTrigger.trigger_taqwa_alert(...)

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from enum import Enum
from threading import RLock
from typing import Callable, Dict, List, Optional
import json


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class TaqwaAlert:
    ts: datetime
    type: str
    description: str
    severity: Severity
    status: str = "unresolved"        # unresolved | resolved | muted
    source: str = "system"
    actor_id: Optional[str] = None
    resolution_note: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ts"] = self.ts.isoformat()
        d["severity"] = self.severity.value
        return d


class TaqwaAlertManager:
    """
    - Toggle signal types (enable/disable)
    - Generate alerts with severity + metadata
    - Rate-limit duplicate spam within a short window
    - Resolve/mute & list recent/unresolved
    - Optional sink hook for side-effects (email/SMS/etc.)
    """

    def __init__(
        self,
        rate_limit_window: timedelta = timedelta(seconds=20),
        sink: Optional[Callable[[TaqwaAlert], None]] = None,
    ):
        self._lock = RLock()
        self._alerts: List[TaqwaAlert] = []
        self._last_emitted: Dict[str, datetime] = {}   # key -> ts
        self._rate_window = rate_limit_window
        self._sink = sink

        # Feature toggles (same spirit as your original)
        self.thresholds: Dict[str, bool] = {
            "low_taqwa_signal": True,
            "unconscious_actions": True,
            "spiritual_neglect": True,
            "guardian_violation": True,        # extra common channel
            "monitor_surge": True,             # surge from activity monitor
        }

    # ---------------- Public API ----------------

    def generate_alert(
        self,
        signal_type: str,
        description: str,
        *,
        severity: Severity = Severity.MEDIUM,
        source: str = "system",
        actor_id: Optional[str] = None,
        rate_limit_key: Optional[str] = None,
    ) -> str:
        """
        Create a taqwa alert if the signal type is enabled and not rate-limited.
        rate_limit_key (optional) groups similar alerts (e.g., by actor or event signature).
        """
        with self._lock:
            if not self.thresholds.get(signal_type, False):
                return f"⚠️ Signal '{signal_type}' is disabled."

            key = rate_limit_key or f"{signal_type}:{description.strip().lower()}"
            last = self._last_emitted.get(key)
            now = _now()
            if last and (now - last) < self._rate_window:
                return "⏳ Alert suppressed (rate-limited)."

            alert = TaqwaAlert(
                ts=now,
                type=signal_type,
                description=description,
                severity=severity,
                source=source,
                actor_id=actor_id,
            )
            self._alerts.append(alert)
            self._last_emitted[key] = now

            # optional side-effect sink (email/SMS/etc.)
            if self._sink:
                try:
                    self._sink(alert)
                except Exception:
                    # keep alerts robust—never fail caller due to sink error
                    pass

            return f"🚨 Taqwa Alert raised [{severity.value}]: {description}"

    # Backwards-compat alias used earlier by DeenGuardianTrigger
    def trigger_taqwa_alert(self, description: str) -> str:
        return self.generate_alert(
            "guardian_violation",
            description,
            severity=Severity.HIGH,
            source="guardian",
        )

    def list_unresolved_alerts(self) -> List[dict]:
        with self._lock:
            return [a.to_dict() for a in self._alerts if a.status == "unresolved"]

    def list_recent(self, limit: int = 20) -> List[dict]:
        with self._lock:
            return [a.to_dict() for a in self._alerts[-limit:]]

    def resolve_alert(self, index: int, resolution_note: str = "") -> str:
        with self._lock:
            if 0 <= index < len(self._alerts):
                self._alerts[index].status = "resolved"
                self._alerts[index].resolution_note = resolution_note
                return f"✅ Alert #{index} resolved."
            return "❌ Invalid alert index."

    def mute_alert(self, index: int, note: str = "") -> str:
        with self._lock:
            if 0 <= index < len(self._alerts):
                self._alerts[index].status = "muted"
                self._alerts[index].resolution_note = note
                return f"🔇 Alert #{index} muted."
            return "❌ Invalid alert index."

    def toggle_alert_type(self, signal_type: str, enable: bool = True) -> str:
        with self._lock:
            if signal_type in self.thresholds:
                self.thresholds[signal_type] = enable
                return f"✅ Taqwa alert for '{signal_type}' {'enabled' if enable else 'disabled'}."
            return f"⚠️ Unknown signal type '{signal_type}'."

    def export_json(self) -> str:
        with self._lock:
            return json.dumps([a.to_dict() for a in self._alerts], ensure_ascii=False, indent=2)
