# memory_debugger.py
# Part of HAIL Phase 2 – Memory & Indexing Engine

from datetime import datetime

class MemoryDebugger:
    def __init__(self):
        self.logs = []

    def log(self, event_type: str, description: str):
        timestamp = datetime.utcnow().isoformat()
        self.logs.append({
            "timestamp": timestamp,
            "event_type": event_type,
            "description": description
        })

    def get_recent_logs(self, limit=10):
        return self.logs[-limit:]

    def clear_logs(self):
        self.logs = []

    def export_logs(self):
        return "\n".join(
            [f"[{log['timestamp']}] {log['event_type']}: {log['description']}" for log in self.logs]
        )

# Example usage
if __name__ == "__main__":
    debugger = MemoryDebugger()
    debugger.log("INDEX", "Phase 2.3 indexed successfully.")
    debugger.log("FILTER", "Qur'an filter applied to message.")
    print(debugger.export_logs())
