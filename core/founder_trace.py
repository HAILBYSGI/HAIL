# core/founder_trace.py

import datetime

class FounderTrace:
    def __init__(self, founder_id="husnain_ali"):
        self.founder_id = founder_id
        self.trace_log = []

    def log_action(self, module, action, source="unknown", override=False):
        entry = {
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "module": module,
            "action": action,
            "source": source,
            "override": override,
            "verified_founder": (source == self.founder_id)
        }
        self.trace_log.append(entry)
        return entry

    def get_all_logs(self):
        return self.trace_log

    def get_logs_by_module(self, module_name):
        return [entry for entry in self.trace_log if entry["module"] == module_name]

    def get_logs_by_source(self, source_id):
        return [entry for entry in self.trace_log if entry["source"] == source_id]

    def verify_last_action(self):
        if not self.trace_log:
            return None
        last = self.trace_log[-1]
        return last["verified_founder"]
