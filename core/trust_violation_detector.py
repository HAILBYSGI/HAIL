class TrustViolationDetector:
    def __init__(self):
        self.violations = []
        self.trust_metrics = {
            "unauthorized_access": True,
            "unverified_command": True,
            "intent_mismatch": True,
            "tampering_detected": True
        }

    def detect_violation(self, category, detail, severity="medium"):
        if category not in self.trust_metrics or not self.trust_metrics[category]:
            return f"⚠️ Trust category '{category}' not active or unknown."

        violation = {
            "category": category,
            "detail": detail,
            "severity": severity,
            "status": "unresolved"
        }
        self.violations.append(violation)
        return f"🚨 Trust Violation Detected: {category} – {detail}"

    def list_unresolved(self):
        return [v for v in self.violations if v["status"] == "unresolved"]

    def resolve_violation(self, index, note=""):
        if 0 <= index < len(self.violations):
            self.violations[index]["status"] = "resolved"
            self.violations[index]["resolution_note"] = note
            return f"✅ Trust violation #{index} resolved."
        return "❌ Invalid violation index."

    def toggle_category(self, category, enable=True):
        if category in self.trust_metrics:
            self.trust_metrics[category] = enable
            status = "enabled" if enable else "disabled"
            return f"✅ Trust detection for '{category}' {status}."
        return f"⚠️ Unknown trust category '{category}'."
