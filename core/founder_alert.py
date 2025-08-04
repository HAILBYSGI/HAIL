# founder_alert.py
# Part of HAIL Phase 3 – AI Ethics, Command & Security Logic

import smtplib
from email.message import EmailMessage
import datetime
import os

class FounderAlert:
    def __init__(self, email_config_path="hail_config/email_settings.txt"):
        self.email_address = None
        self.email_password = None
        self.load_email_config(email_config_path)

    def load_email_config(self, path):
        """
        Loads the founder's email credentials from a secure config file.
        """
        if not os.path.exists(path):
            raise FileNotFoundError("Email configuration file not found.")
        
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
            self.email_address = lines[0].strip()
            self.email_password = lines[1].strip()

    def send_alert(self, subject, message_body):
        """
        Sends an alert email to the Founder.
        """
        if not self.email_address or not self.email_password:
            raise ValueError("Email credentials not loaded.")

        msg = EmailMessage()
        msg["Subject"] = f"HAIL ALERT: {subject}"
        msg["From"] = self.email_address
        msg["To"] = self.email_address  # Can also add backup emails here
        msg.set_content(f"{message_body}\n\nTimestamp: {datetime.datetime.now()}")

        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
                smtp.login(self.email_address, self.email_password)
                smtp.send_message(msg)
            return True
        except Exception as e:
            print(f"Email alert failed: {e}")
            return False

# Example usage
if __name__ == "__main__":
    alert = FounderAlert()
    alert.send_alert("Unauthorized Access Attempt", "HAIL detected a failed override attempt on a protected module.")
