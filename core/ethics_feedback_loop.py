class EthicsFeedbackLoop:
    def __init__(self):
        self.log = []
        self.feedback_sources = {
            "founder": True,
            "shariah_board": True,
            "users": False  # Optional feedback from general users
        }

    def record_feedback(self, source, message, severity="medium"):
        if source not in self.feedback_sources or not self.feedback_sources[source]:
            return f"Feedback source '{source}' not authorized or disabled."

        entry = {
            "source": source,
            "message": message,
            "severity": severity,
            "status": "pending_review"
        }
        self.log.append(entry)
        return "✅ Feedback recorded for review."

    def review_feedback(self):
        pending = [entry for entry in self.log if entry["status"] == "pending_review"]
        return pending if pending else ["✅ No pending feedback."]

    def resolve_feedback(self, index, decision):
        if 0 <= index < len(self.log):
            self.log[index]["status"] = "resolved"
            self.log[index]["decision"] = decision
            return f"✅ Feedback #{index} resolved."
        return "⚠️ Invalid feedback index."

    def enable_feedback_source(self, source):
        self.feedback_sources[source] = True
        return f"✅ Feedback from '{source}' enabled."

    def disable_feedback_source(self, source):
        self.feedback_sources[source] = False
        return f"✅ Feedback from '{source}' disabled."
