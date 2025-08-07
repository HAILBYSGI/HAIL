class InternalWarningDispatcher:
    def __init__(self):
        self.warning_log = []

    def dispatch_warning(self, source, message, level="medium"):
        warning = {
            "source": source,
            "message": message,
            "level": level,
            "status": "active"
        }
        self.warning_log.append(warning)

        if level == "high":
            self.trigger_emergency_protocol(warning)

        return {
            "status": "dispatched",
            "warning": warning
        }

    def trigger_emergency_protocol(self, warning):
        # Simulate sending urgent alert to Founder
        print(f"🚨 EMERGENCY WARNING: {warning['message']} (Source: {warning['source']})")

    def get_all_warnings(self):
        return self.warning_log

    def clear_warnings(self):
        self.warning_log = []
        return "✅ All internal warnings cleared."
