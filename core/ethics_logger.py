# core/ethics_logger.py

import datetime
import os

class EthicsLogger:
    def __init__(self, log_dir="hail/logs"):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self.log_file = os.path.join(log_dir, "ethics_log.txt")

    def log_event(self, event_type, description, system_module, severity="medium", tags=None):
        timestamp = datetime.datetime.utcnow().isoformat()
        tags = tags if tags else []

        log_entry = {
            "timestamp": timestamp,
            "event_type": event_type,
            "system_module": system_module,
            "description": description,
            "severity": severity,
            "tags": tags
        }

        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(self._format_log_entry(log_entry) + "\n")

        return log_entry

    def _format_log_entry(self, entry):
        return f"[{entry['timestamp']}] [{entry['event_type'].upper()}] ({entry['system_module']}) [{entry['severity'].upper()}] :: {entry['description']} Tags: {', '.join(entry['tags'])}"

    def get_logs(self, filter_by=None):
        if not os.path.exists(self.log_file):
            return []

        with open(self.log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        if filter_by:
            return [line for line in lines if filter_by in line]
        return lines
