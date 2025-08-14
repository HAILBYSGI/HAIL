# core/founder_alert.py
# HAIL — FounderAlert (Upgraded)
from __future__ import annotations

import json
import os
import smtplib
import ssl
import time
from configparser import ConfigParser
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Optional

# Optional sink (best-effort)
try:
    from core.action_logger import ActionLogger  # type: ignore
except Exception:  # pragma: no cover
    ActionLogger = None  # type: ignore


@dataclass
class SMTPConfig:
    email: str
    password: str
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465
    use_ssl: bool = True
    to: Optional[str] = None  # default to same as email if None

    @staticmethod
    def from_env() -> Optional["SMTPConfig"]:
        email = os.getenv("HAIL_EMAIL")
        password = os.getenv("HAIL_EMAIL_PASSWORD")
        if not (email and password):
            return None
        host = os.getenv("HAIL_SMTP_HOST", "smtp.gmail.com")
        port = int(os.getenv("HAIL_SMTP_PORT", "465"))
        use_ssl = os.getenv("HAIL_SMTP_SSL", "1") != "0"
        to = os.getenv("HAIL_EMAIL_TO", None)
        return SMTPConfig(email=email, password=password, smtp_host=host, smtp_port=port, use_ssl=use_ssl, to=to)


class FounderAlert:
    """
    Sends critical alerts to the Founder.
    - Loads credentials from ENV first, then from a config file:
        * TXT (2 lines: email, password)
        * INI (section [smtp] with keys)
        * JSON (object with keys)
    - Cooldown to prevent spam
    - Optional sinks: ActionLogger + Mission Log
    """

    def __init__(
        self,
        email_config_path: str = "hail_config/email_settings.txt",
        *,
        cooldown_seconds: int = 5,
        mission_log_sink: Optional[callable] = None,  # lambda payload: mission_log.append(...)
    ) -> None:
        self._lock = RLock()
        self._cooldown = max(0, int(cooldown_seconds))
        self._last_sent_at = 0.0
        self._mission_log_sink = mission_log_sink

        # Optional sink
        self._action_logger = ActionLogger() if ActionLogger else None

        # Load configuration (ENV first)
        env_cfg = SMTPConfig.from_env()
        if env_cfg:
            self._cfg = env_cfg
        else:
            self._cfg = self._load_email_config(Path(email_config_path))

    # ---------- Public API ----------

    def send_alert(self, subject: str, message_body: str) -> Dict[str, Any]:
        """
        Primary method (kept from your original code).
        Returns a structured result dict.
        """
        return self._send(subject, message_body)

    # Alias for compatibility (other modules call .send(...))
    def send(self, subject: str, message_body: str) -> Dict[str, Any]:
        return self._send(subject, message_body)

    # ---------- Internals ----------

    def _send(self, subject: str, message_body: str) -> Dict[str, Any]:
        with self._lock:
            now = time.time()
            if self._cooldown and (now - self._last_sent_at) < self._cooldown:
                return {"ok": False, "error": "cooldown_active", "cooldown_seconds": self._cooldown}

            if not (self._cfg and self._cfg.email and self._cfg.password):
                return {"ok": False, "error": "credentials_missing"}

            to_addr = self._cfg.to or self._cfg.email

            msg = EmailMessage()
            msg["Subject"] = f"HAIL ALERT: {subject}"
            msg["From"] = self._cfg.email
            msg["To"] = to_addr
            msg.set_content(f"{message_body}\n\nTimestamp (UTC): {datetime.now(timezone.utc).isoformat()}")

            try:
                if self._cfg.use_ssl:
                    context = ssl.create_default_context()
                    with smtplib.SMTP_SSL(self._cfg.smtp_host, self._cfg.smtp_port, context=context) as smtp:
                        smtp.login(self._cfg.email, self._cfg.password)
                        smtp.send_message(msg)
                else:
                    with smtplib.SMTP(self._cfg.smtp_host, self._cfg.smtp_port) as smtp:
                        smtp.starttls(context=ssl.create_default_context())
                        smtp.login(self._cfg.email, self._cfg.password)
                        smtp.send_message(msg)

                self._last_sent_at = now
                self._sink_action("FounderAlert", subject, "SENT")
                self._sink_mission("founder_alert", subject, verdict="halal", score=0.05)

                return {"ok": True, "to": to_addr, "subject": subject}

            except Exception as e:
                err = repr(e)
                self._sink_action("FounderAlert", f"ERROR: {subject}", "FAILED", reason=err)
                self._sink_mission("founder_alert_error", subject, verdict="shubha", score=0.35, reason=err)
                return {"ok": False, "error": err}

    def _load_email_config(self, path: Path) -> SMTPConfig:
        if not path.exists():
            raise FileNotFoundError(f"Email configuration not found at: {path}")

        # Try JSON
        if path.suffix.lower() == ".json":
            obj = json.loads(path.read_text(encoding="utf-8"))
            return SMTPConfig(
                email=obj["email"],
                password=obj["password"],
                smtp_host=obj.get("smtp_host", "smtp.gmail.com"),
                smtp_port=int(obj.get("smtp_port", 465)),
                use_ssl=bool(obj.get("use_ssl", True)),
                to=obj.get("to"),
            )

        # Try INI
        if path.suffix.lower() in (".ini", ".cfg"):
            cp = ConfigParser()
            cp.read(path, encoding="utf-8")
            s = cp["smtp"]
            return SMTPConfig(
                email=s.get("email"),
                password=s.get("password"),
                smtp_host=s.get("smtp_host", "smtp.gmail.com"),
                smtp_port=s.getint("smtp_port", 465),
                use_ssl=s.getboolean("use_ssl", True),
                to=s.get("to", None),
            )

        # Default TXT (2 lines): email, password
        lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if len(lines) < 2:
            raise ValueError("TXT config must have at least two lines: email, password")
        return SMTPConfig(email=lines[0], password=lines[1])

    # ---------- Sinks ----------

    def _sink_action(self, action_type: str, subject: str, status: str, *, reason: str = "") -> None:
        if not self._action_logger:
            return
        try:
            self._action_logger.log(
                action_type=action_type,
                user_input=subject[:160],
                system_decision=status,
                module="founder_alert",
                reason=reason[:300],
                status="Success" if status == "SENT" else "Error",
            )
        except Exception:
            pass

    def _sink_mission(self, activity: str, subject: str, *, verdict: str, score: float, reason: str = "") -> None:
        if not self._mission_log_sink:
            return
        try:
            self._mission_log_sink({
                "actor_id": "system:alert",
                "activity": activity,
                "verdict": verdict,
                "score": float(score),
                "reasons": [subject[:120]] + ([reason[:120]] if reason else []),
                "tags": ["alert", "founder"],
                "payload": {"subject": subject},
            })
        except Exception:
            pass


# ------------- Minimal self-test -------------
if __name__ == "__main__":
    # Ensure env vars or config file exist before running
    fa = FounderAlert()
    print(fa.send("Test alert", "This is a test from HAIL FounderAlert."))
