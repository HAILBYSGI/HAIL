import smtplib
from email.mime.text import MIMEText
from core.founder_alert import FounderAlert

class DeenAlertBroadcast:
    def __init__(self, email_config):
        self.email_config = email_config
        self.alert = FounderAlert()

    def send_broadcast(self, subject, message, recipients):
        """
        Sends a broadcast email to all listed recipients with deen-related alerts or reminders.
        """
        try:
            msg = MIMEText(message)
            msg['Subject'] = subject
            msg['From'] = self.email_config['sender']
            msg['To'] = ", ".join(recipients)

            with smtplib.SMTP_SSL(self.email_config['smtp_server'], self.email_config['smtp_port']) as server:
                server.login(self.email_config['sender'], self.email_config['password'])
                server.sendmail(self.email_config['sender'], recipients, msg.as_string())

            self.alert.send("📢 Deen Alert Broadcast Sent", f"Message: {subject}")
            return {"status": "success", "recipients": recipients, "subject": subject}

        except Exception as e:
            self.alert.send("❌ Deen Alert Broadcast Failed", str(e))
            return {"status": "error", "message": str(e)}
