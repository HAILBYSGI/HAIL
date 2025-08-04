# action_logger.py
# Part of HAIL Phase 3 – AI Ethics, Command & Security Logic

import datetime
import os

class ActionLogger:
    def __init__(self, log_path="hail_logs/action_log.txt"):
        self.log_path = log_path
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)

    def log(self, action_type, user_input, system_decision, module, reason, status):
        """
        Logs an entry with all relevant metadata.
        """
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        entry = (
            f"---\n"
            f"Timestamp      : {timestamp}\n"
            f"Action Type    : {action_type}\n"
            f"User Input     : {user_input}\n"
            f"System Decision: {system_decision}\n"
            f"Handled By     : {module}\n"
            f"Reason         : {reason}\n"
            f"Status         : {status}\n"
        )

        with open(self.log_path, "a", encoding="utf-8") as file:
            file.write(entry + "\n")

        return {"status": "LOGGED", "timestamp": timestamp}

# Example usage
if __name__ == "__main__":
    logger = ActionLogger()
    logger.log(
        action_type="Command Execution",
        user_input="Send charity request to Ummah Center",
        system_decision="APPROVED",
        module="shariah_guard",
        reason="Halal intent and validated source",
        status="Success"
    )
