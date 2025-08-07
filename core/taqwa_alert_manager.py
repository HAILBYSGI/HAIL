class TaqwaAlertManager:
    def __init__(self):
        self.alert_log = []
        self.thresholds = {
            "low_taqwa_signal": True,
            "unconscious_actions": True,
            "spiritual_neglect": True
        }

    def generate_alert(self, signal_type, description):
        if signal_type not in self.thresholds or not self.thresholds[signal_type]:
            return f"⚠️ Signal type '{signal_type}' is not active for alerts."

        alert = {
            "type": signal_type,
            "description": description,
            "status": "unresolved"
        }
        self.alert_log.append(alert)
        return f"🚨 Taqwa Alert raised: {description}"

    def list_unresolved_alerts(self):
        return [a for a in self.alert_log if a["status"] == "unresolved"]

    def resolve_alert(self, index, resolution_note=""):
        if 0 <= index < len(self.alert_log):
            self.alert_log[index]["status"] = "resolved"
            self.alert_log[index]["resolution_note"] = resolution_note
            return f"✅ Alert #{index} resolved."
        return "❌ Invalid alert index."

    def toggle_alert_type(self, signal_type, enable=True):
        if signal_type in self.thresholds:
            self.thresholds[signal_type] = enable
            state = "enabled" if enable else "disabled"
            return f"✅ Taqwa alert for '{signal_type}' {state}."
        return f"⚠️ Unknown signal type '{signal_type}'."
