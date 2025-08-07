# core/shariah_violation_notifier.py

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from hail.config import email_secrets

class ShariahViolationNotifier:
    def __init__(self):
        self.smtp_server = email_secrets.SMTP_SERVER
        self.smtp_port = email_secrets.SMTP_PORT
        self.sender_email = email_secrets.EMAIL_SENDER
        self.password = email_secrets.EMAIL_PASSWORD
        self.receiver_email = email_secrets.EMAIL_RECEIVER

    def send_alert(self, subject, message):
        try:
            # Compose email
            msg = MIMEMultipart()
            msg["From"] = self.sender_email
            msg["To"] = self.receiver_email
            msg["Subject"] = subject

            msg.attach(MIMEText(message, "plain"))

            # Send email securely
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port, context=context) as server:
                server.login(self.sender_email, self.password)
                server.sendmail(self.sender_email, self.receiver_email, msg.as_string())

            print("✅ Shari'ah violation alert sent successfully.")

        except Exception as e:
            print(f"❌ Failed to send alert: {e}")
