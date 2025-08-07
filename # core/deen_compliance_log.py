import datetime
import json
import os

class DeenComplianceLogger:
    def __init__(self, log_file="hail/logs/deen_compliance_log.json"):
        self.log_file = log_file
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        if not os.path.exists(self.log_file):
            with open(self.log_file, "w") as f:
                json.dump([], f)

    def log_entry(self, module, action, result, compliant, notes=None):
        entry = {
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "module": module,
            "action": action,
            "result": result,
            "deen_compliant": compliant,
            "notes": notes
        }

        try:
            with open(self.log_file, "r") as f:
                logs = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            logs = []

        logs.append(entry)

        with open(self.log_file, "w") as f:
            json.dump(logs, f, indent=4)

        print(f"📝 Deen Compliance Log updated: {entry['timestamp']}")

    def get_latest_logs(self, count=10):
        try:
            with open(self.log_file, "r") as f:
                logs = json.load(f)
            return logs[-count:]
        except Exception as e:
            print(f"❌ Error reading Deen Compliance Logs: {e}")
            return []
