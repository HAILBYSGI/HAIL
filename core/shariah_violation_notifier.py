# core/shariah_violation_notifier.py
# Sends high-priority alerts when a Shari'ah violation is detected.
# - Prefers hail/config/email_config.py
# - Falls back to environment variables if needed
# - Minimal, dependency-free (stdlib only)

from __future__ import annotations

import os
import smtplib
import ssl
from typing import Optional, Dict
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def _load_email_settings() -> Dict[str, str]:
    """
    Try multiple shapes so we work with different config styles:
    1) hail/config/email_config.py with attributes:
       SMTP_SERVER, SMTP_PORT, EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECEIVER
    2) hail/config/email_config.py with dict EMAIL or EMAIL_CONFIG
    3) Environment variables (HAIL_*)

    Returns a dict with keys:
      smtp_server, smtp_port, sender, password, receiver
    Raises RuntimeError if required values are missing.
    """
    # Attempt 1/2: module-based config
    try:
        from hail.config import email_config as cfg  # type: ignore
        # attribute style
        server = getattr(cfg, "SMTP_SERVER", None)
        port = getattr(cfg, "SMTP_PORT", None)
        sender = getattr(cfg, "EMAIL_SENDER", None)
        password = getattr(cfg, "EMAIL_PASSWORD", None)
        receiver = getattr(cfg, "EMAIL_RECEIVER", None)

        # dict style
        if not all([server, port, sender, password, receiver]):
            for key in ("EMAIL", "EMAIL_CONFIG", "CONFIG"):
                d = getattr(cfg, key, None)
                if isinstance(d, dict):
                    server = server or d.get("SMTP_SERVER")
                    port = port or d.get("SMTP_PORT")
                    sender = sender or d.get("EMAIL_SENDER")
                    password = password or d.get("EMAIL_PASSWORD")
                    receiver = receiver or d.get("EMAIL_RECEIVER")

        if all([server, port, sender, password, receiver]):
            return {
                "smtp_server": str(server),
                "smtp_port": int(port),
                "sender": str(sender),
                "password": str(password),
                "receiver": str(receiver),
            }
    except Exception:
        pass  # fall through to env

    # Attempt 3: environment variables
    server = os.getenv("HAIL_SMTP_SERVER")
    port = os.getenv("HAIL_SMTP_PORT")
    sender = os.getenv("HAIL_EMAIL_SENDER")
    password = os.getenv("HAIL_EMAIL_PASSWORD")
    receiver = os.getenv("HAIL_EMAIL_RECEIVER")

    if all([server, port, sender, password, receiver]):
        return {
            "smtp_server": server,
            "smtp_port": int(port),
            "sender": sender,
            "password": password,
            "receiver": receiver,
        }

    raise RuntimeError(
        "Email settings not found. Provide hail/config/email_config.py with either "
        "attributes (SMTP_SERVER/SMTP_PORT/EMAIL_SENDER/EMAIL_PASSWORD/EMAIL_RECEIVER) "
        "or dict EMAIL/EMAIL_CONFIG, or set env vars HAIL_SMTP_SERVER, HAIL_SMTP_PORT, "
        "HAIL_EMAIL_SENDER, HAIL_EMAIL_PASSWORD, HAIL_EMAIL_RECEIVER."
    )


class ShariahViolationNotifier:
    def __init__(
        self,
        smtp_server: Optional[str] = None,
        smtp_port: Optional[int] = None,
        sender_email: Optional[str] = None,
        password: Optional[str] = None,
        receiver_email: Optional[str] = None,
    ):
        # Allow explicit overrides, otherwise load from config/env
        if all([smtp_server, smtp_port, sender_email, password, receiver_email]):
            self.smtp_server = str(smtp_server)
            self.smtp_port = int(smtp_port)  # must be SSL port (e.g., 465)
            self.sender_email = str(sender_email)
            self.password = str(password)
            self.receiver_email = str(receiver_email)
        else:
            settings = _load_email_settings()
            self.smtp_server = settings["smtp_server"]
            self.smtp_port = settings["smtp_port"]
            self.sender_email = settings["sender"]
            self.password = settings["password"]
            self.receiver_email = settings["receiver"]

    def send_alert(self, subject: str, message: str) -> bool:
        """
        Send a high-priority Shari'ah violation alert.
        Returns True on success, False on failure (and prints minimal error).
        """
        try:
            msg = MIMEMultipart()
            msg["From"] = self.sender_email
            msg["To"] = self.receiver_email
            msg["Subject"] = subject
            msg.attach(MIMEText(message, "plain"))

            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port, context=context) as server:
                server.login(self.sender_email, self.password)
                server.sendmail(self.sender_email, [self.receiver_email], msg.as_string())

            print("✅ Shari'ah violation alert sent.")
            return True
        except Exception as e:
            print(f"❌ Failed to send alert: {e}")
            return False


# --- Quick self-test (optional) ---
if __name__ == "__main__":
    try:
        notifier = ShariahViolationNotifier()  # uses config/env
        notifier.send_alert(
            "Test — Shari'ah Violation",
            "This is a test alert from ShariahViolationNotifier."
        )
    except Exception as ex:
        print(f"[config error] {ex}")
