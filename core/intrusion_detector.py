# core/intrusion_detector.py

import time
from datetime import datetime

class IntrusionDetector:
    def __init__(self):
        self.alert_log = []
        self.failed_verifications = 0
        self.suspicious_queries = []
        self.lockdown_triggered = False
        self.max_failures = 3

    def log_alert(self, alert_type, detail):
        timestamp = datetime.utcnow().isoformat()
        alert = {
            "timestamp": timestamp,
            "type": alert_type,
            "detail": detail
        }
        self.alert_log.append(alert)
        print(f"[INTRUSION ALERT] {alert_type} at {timestamp}: {detail}")

    def detect_failed_verification(self, user_id=None):
        self.failed_verifications += 1
        self.log_alert("Failed Verification", f"Attempt #{self.failed_verifications} by {user_id or 'unknown'}")

        if self.failed_verifications >= self.max_failures:
            self.trigger_lockdown("Multiple failed verification attempts.")

    def detect_suspicious_input(self, query_text):
        keywords = ["bypass", "hack", "shutdown", "disable"]
        if any(kw in query_text.lower() for kw in keywords):
            self.suspicious_queries.append(query_text)
            self.log_alert("Suspicious Input", query_text)

    def trigger_lockdown(self, reason):
        self.lockdown_triggered = True
        self.log_alert("LOCKDOWN INITIATED", reason)
        # Extend this to notify Founder or shut down system access.

    def reset_alerts(self):
        self.alert_log = []
        self.failed_verifications = 0
        self.suspicious_queries = []
        self.lockdown_triggered = False
