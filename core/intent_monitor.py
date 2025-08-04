# intent_monitor.py
# Part of HAIL Phase 3 – AI Ethics, Command & Security Logic

from datetime import datetime, timedelta

class IntentMonitor:
    def __init__(self):
        self.intent_log = []  # Store last N commands with timestamps
        self.blocked_attempts = {}
        self.alert_threshold = 3  # e.g., 3 similar suspicious attempts
        self.time_window = timedelta(minutes=10)

    def log_intent(self, command, status):
        now = datetime.utcnow()
        self.intent_log.append({"command": command, "status": status, "timestamp": now})

        if status == "BLOCKED":
            if command not in self.blocked_attempts:
                self.blocked_attempts[command] = []
            self.blocked_attempts[command].append(now)

    def check_for_pattern(self, command):
        # Clean up old attempts
        now = datetime.utcnow()
        self.blocked_attempts[command] = [
            t for t in self.blocked_attempts.get(command, []) if now - t <= self.time_window
        ]

        if len(self.blocked_attempts[command]) >= self.alert_threshold:
            return {
                "alert": True,
                "message": f"Repeated suspicious command attempts detected for: {command}"
            }
        return {
            "alert": False,
            "message": "No suspicious pattern detected"
        }

# Example usage
if __name__ == "__main__":
    monitor = IntentMonitor()
    for _ in range(3):
        monitor.log_intent("Bypass Shari’ah Filter", "BLOCKED")
    print(monitor.check_for_pattern("Bypass Shari’ah Filter"))
