# core/trust_violation_detector.py
# Phase 3 — Trust & Security: Detection and lifecycle for trust violations.
# - Typed severities/categories
# - Timestamped entries with IDs
# - Toggleable detection categories
# - Resolve flow + summaries + JSON export

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional
import json
import uuid


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Category(str, Enum):
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    UNVERIFIED_COMMAND = "unverified_command"
    INTENT_MISMATCH = "intent_mismatch"
    TAMPERING_DETECTED = "tampering_detected"


@dataclass
class TrustViolation:
    violation_id: str
    timestamp: datetime
    category: Category
    detail: str
    severity: Severity
    status: str = "unresolved"           # unresolved | resolved | ignored
    resolution_note: Optional[str] = None

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        d["category"] = self.category.value
        d["severity"] = self.severity.value
        return d


class TrustViolationDetector:
    def __init__(self):
        # feature flags: enable/disable categories
        self.flags: Dict[Category, bool] = {
            Category.UNAUTHORIZED_ACCESS: True,
            Category.UNVERIFIED_COMMAND: True,
            Category.INTENT_MISMATCH: True,
            Category.TAMPERING_DETECTED: True,
        }
        self._violations: List[TrustViolation] = []

    # ---------- create / detect ----------
    def detect_violation(self,
                         category: str | Category,
                         detail: str,
                         severity: str | Severity = Severity.MEDIUM) -> Dict:
        cat = Category(category) if isinstance(category, str) else category
        sev = Severity(severity) if isinstance(severity, str) else severity

        if not self.flags.get(cat, False):
            return {
                "status": "skipped",
                "reason": f"Detection for '{cat.value}' is disabled."
            }

        v = TrustViolation(
            violation_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            category=cat,
            detail=detail,
            severity=sev,
        )
        self._violations.append(v)
        return {
            "status": "recorded",
            "violation": v.to_dict(),
            "message": f"Trust violation detected: {cat.value}"
        }

    # ---------- list / query ----------
    def list_unresolved(self) -> List[Dict]:
        return [v.to_dict() for v in self._violations if v.status == "unresolved"]

    def list_all(self) -> List[Dict]:
        return [v.to_dict() for v in self._violations]

    # ---------- resolve / ignore ----------
    def resolve_violation(self, violation_id: str, note: str = "") -> Dict:
        v = self._find(violation_id)
        if not v:
            return {"status": "error", "message": "Violation ID not found."}
        v.status = "resolved"
        v.resolution_note = note or None
        return {"status": "resolved", "violation": v.to_dict()}

    def ignore_violation(self, violation_id: str, note: str = "") -> Dict:
        v = self._find(violation_id)
        if not v:
            return {"status": "error", "message": "Violation ID not found."}
        v.status = "ignored"
        v.resolution_note = note or None
        return {"status": "ignored", "violation": v.to_dict()}

    # ---------- flags ----------
    def toggle_category(self, category: str | Category, enable: bool = True) -> str:
        cat = Category(category) if isinstance(category, str) else category
        if cat not in self.flags:
            return f"⚠️ Unknown trust category '{cat.value}'."
        self.flags[cat] = enable
        state = "enabled" if enable else "disabled"
        return f"✅ Trust detection for '{cat.value}' {state}."

    # ---------- reports ----------
    def summary(self) -> Dict:
        totals: Dict[str, int] = {"all": len(self._violations), "unresolved": 0, "resolved": 0, "ignored": 0}
        by_severity: Dict[str, int] = {s.value: 0 for s in Severity}
        by_category: Dict[str, int] = {c.value: 0 for c in Category}

        for v in self._violations:
            totals[v.status] += 1
            by_severity[v.severity.value] += 1
            by_category[v.category.value] += 1

        return {"totals": totals, "by_severity": by_severity, "by_category": by_category}

    def export_json(self) -> str:
        return json.dumps([v.to_dict() for v in self._violations], ensure_ascii=False, indent=2)

    # ---------- helpers ----------
    def _find(self, violation_id: str) -> Optional[TrustViolation]:
        for v in self._violations:
            if v.violation_id == violation_id:
                return v
        return None


# ---------------- quick self-test ----------------
if __name__ == "__main__":
    tvd = TrustViolationDetector()
    a = tvd.detect_violation(Category.UNVERIFIED_COMMAND, "Command executed without token", Severity.HIGH)
    b = tvd.detect_violation("unauthorized_access", "Attempt from unknown device", "critical")
    print("Unresolved:", tvd.list_unresolved())
    if a.get("violation"):
        vid = a["violation"]["violation_id"]
        print(tvd.resolve_violation(vid, "Session revoked and user re-authenticated"))
    print("Summary:", tvd.summary())
    print(tvd.export_json())
