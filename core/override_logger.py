# core/override_logger.py

import datetime
import os

class OverrideLogger:
    def __init__(self, log_dir="hail/logs"):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self.log_file = os.path.join(log_dir, "override_events.txt")

    def log_override(self, reason, system_module, attempted_action, user_input=None, outcome="Blocked"):
        timestamp = datetime.datetime.utcnow().isoformat()

        log_entry = {
            "timestamp": timestamp,
            "reason": reason,
            "system_module": system_module,
            "attempted_action": attempted_action,
            "user_input": user_input or "N/A",
            "outcome": outcome
        }

        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(self._format_log_entry(log_entry) + "\n")

        return log_entry

    def _format_log_entry(self, entry):
        return (f"[{entry['timestamp']}] [OVERRIDE] ({entry['system_module']}) :: "
                f"Action: {entry['attempted_action']} | Reason: {entry['reason']} | "
                f"Input: {entry['user_input']} | Outcome: {entry['outcome']}")

    def get_override_logs(self, filter_by=None):
        if not os.path.exists(self.log_file):
            return []

        with open(self.log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        if filter_by:
            return [line for line in lines if filter_by.lower() in line.lower()]
        return lines
