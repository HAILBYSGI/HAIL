import datetime
import json
import os

class DeenViolationLogger:
    def __init__(self, log_file="hail/logs/deen_violations.json"):
        self.log_file = log_file
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        if not os.path.exists(self.log_file):
            with open(self.log_file, "w") as f:
                json.dump([], f)

    def log_violation(self, module, action, reason, level="critical"):
        violation_entry = {
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "module": module,
            "action": action,
            "reason": reason,
            "level": level
        }

        try:
            with open(self.log_file, "r") as f:
                logs = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            logs = []

        logs.append(violation_entry)

        with open(self.log_file, "w") as f:
            json.dump(logs, f, indent=4)

        print(f"🚨 Deen violation recorded: {violation_entry}")

    def get_recent_violations(self, count=10):
        try:
            with open(self.log_file, "r") as f:
                logs = json.load(f)
            return logs[-count:]
        except Exception as e:
            print(f"❌ Error reading Deen Violation Logs: {e}")
            return []
