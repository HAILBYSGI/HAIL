# secure_logger.py
# Part of HAIL Phase 3 – AI Ethics, Command & Security Logic

import os
import json
from datetime import datetime
from cryptography.fernet import Fernet

class SecureLogger:
    def __init__(self, key_file='core/logger_key.key', log_dir='logs/'):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)

        # Load or create encryption key
        if not os.path.exists(key_file):
            self.key = Fernet.generate_key()
            with open(key_file, 'wb') as f:
                f.write(self.key)
        else:
            with open(key_file, 'rb') as f:
                self.key = f.read()

        self.cipher = Fernet(self.key)

    def log(self, module, action, status, metadata=None):
        timestamp = datetime.utcnow().isoformat()
        log_entry = {
            "timestamp": timestamp,
            "module": module,
            "action": action,
            "status": status,
            "metadata": metadata or {}
        }

        # Convert to encrypted log line
        json_log = json.dumps(log_entry)
        encrypted_log = self.cipher.encrypt(json_log.encode())

        filename = os.path.join(self.log_dir, f"log_{datetime.utcnow().date()}.log")
        with open(filename, 'ab') as f:
            f.write(encrypted_log + b'\n')

        return True

# Example usage
if __name__ == "__main__":
    logger = SecureLogger()
    logger.log(
        module="ActionBlocker",
        action="Blocked non-halal command",
        status="BLOCKED",
        metadata={"command": "Play music", "reason": "Shari’ah violation"}
    )
