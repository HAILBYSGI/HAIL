# core/deen_alert_broadcast.py
# HAIL — DeenAlertBroadcast (Upgraded)

from __future__ import annotations

import re
import smtplib
import time
from dataclasses import dataclass, asdict
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, Iterable, List, Optional, Tuple

from core.founder_alert import FounderAlert

try:
    from core.action_logger import ActionLogger
except Exception:  # pragma: no cover
    ActionLogger = None  # type: ignore


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass
class BroadcastReport:
    status: str                    # "success" | "partial" | "error"
    subject: str
    recipients_sent: List[str]
    recipients_skipped: List[Tuple[str, str]]  # (email, reason)
    batches: int
    attempts: int
    dry_run: bool
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "subject": self.subject,
            "recipients_sent": list(self.recipients_sent),
            "recipients_skipped": list(self.recipients_skipped),
            "batches": self.batches,
            "attempts": self.attempts,
            "dry_run": self.dry_run,
            "error": self.error,
        }


class DeenAlertBroadcast:
    """
    Secure broadcast of deen-related alerts (email).
    Safety features:
      - email validation & dedupe
      - batching to avoid provider limits
      - dry_run mode for testing
      - HTML + plain text
      - retries with small backoff
      - ActionLogger + FounderAlert + MissionLog (optional)
    """

    def __init__(
        self,
        email_config: Dict[str, Any],
        *,
        batch_size: int = 50,
        timeout: int = 20,
        retries: int = 2,
        action_logger: Optional["ActionLogger"] = None,
        mission_log_sink: Optional[callable] = None,  # lambda d: mission_log.append(...)
    ) -> None:
        """
        email_config should provide:
          {
            "sender": "...",
            "password": "...",
            "smtp_server": "...",
            "smtp_port": 465
          }
        """
        self.email_config = email_config
        self.batch_size = max(1, int(batch_size))
        self.timeout = int(timeout)
        self.retries = max(0, int(retries))
        self.alert = FounderAlert()
        self.log = action_logger
        self.mission_log_sink = mission_log_sink

    # ---------------- public API ----------------

    def send_broadcast(
        self,
        subject: str,
        message: str,
        recipients: Iterable[str],
        *,
        html: Optional[str] = None,
        cc: Optional[Iterable[str]] = None,
        bcc: Optional[Iterable[str]] = None,
        dry_run: bool = False,
        tags: Optional[List[str]] = None,
        reply_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a broadcast email. Returns a BroadcastReport dict.
        - If html is provided, email is multipart (plain + HTML).
        - dry_run=True validates & logs but does not send.
        """
        all_targets, skipped = self._prepare_recipients(recipients, cc, bcc)
        batches = [all_targets[i : i + self.batch_size] for i in range(0, len(all_targets), self.batch_size)] or [[]]

        attempts = 0
        sent_total: List[str] = []

        # Build message template once
        base_msg = self._build_message(subject, message, html, reply_to)

        if dry_run:
            rep = BroadcastReport(
                status="success",
                subject=subject,
                recipients_sent=[*all_targets],
                recipients_skipped=skipped,
                batches=len(batches) if all_targets else 0,
                attempts=attempts,
                dry_run=True,
            )
            self._sinks(rep, tags)
            return rep.to_dict()

        # Real sending
        try:
            with smtplib.SMTP_SSL(self.email_config["smtp_server"], int(self.email_config["smtp_port"]), timeout=self.timeout) as server:
                server.login(self.email_config["sender"], self.email_config["password"])

                for batch in batches:
                    if not batch:
                        continue
                    ok = False
                    for attempt in range(self.retries + 1):
                        attempts += 1
                        try:
                            msg = base_msg  # reuse structure
                            msg.replace_header("To", ", ".join(batch)) if msg["To"] else msg.add_header("To", ", ".join(batch))
                            server.sendmail(self.email_config["sender"], batch, msg.as_string())
                            sent_total.extend(batch)
                            ok = True
                            break
                        except Exception as e:
                            if attempt < self.retries:
                                time.sleep(1.0 + attempt * 1.5)
                            else:
                                # mark all in batch as failed
                                for addr in batch:
                                    skipped.append((addr, f"send_failed: {type(e).__name__}"))
                    if not ok:
                        # continue to next batch; partial result
                        pass

            status = "success" if sent_total and len(skipped) == 0 else ("partial" if sent_total else "error")
            rep = BroadcastReport(
                status=status,
                subject=subject,
                recipients_sent=sorted(set(sent_total)),
                recipients_skipped=skipped,
                batches=len(batches) if all_targets else 0,
                attempts=attempts,
                dry_run=False,
                error=None if status != "error" else "All batches failed",
            )
            self._sinks(rep, tags)
            return rep.to_dict()

        except Exception as e:
            rep = BroadcastReport(
                status="error",
                subject=subject,
                recipients_sent=sorted(set(sent_total)),
                recipients_skipped=skipped,
                batches=len(batches) if all_targets else 0,
                attempts=attempts,
                dry_run=False,
                error=f"{type(e).__name__}: {e}",
            )
            self._sinks(rep, tags)
            return rep.to_dict()

    # ---------------- helpers ----------------

    def _prepare_recipients(
        self,
        to: Iterable[str],
        cc: Optional[Iterable[str]],
        bcc: Optional[Iterable[str]],
    ) -> Tuple[List[str], List[Tuple[str, str]]]:
        dedup: Dict[str, None] = {}
        skipped: List[Tuple[str, str]] = []

        def add_many(items: Optional[Iterable[str]], label: str) -> None:
            if not items:
                return
            for raw in items:
                if not raw:
                    continue
                email = str(raw).strip()
                if not _EMAIL_RE.match(email):
                    skipped.append((email, f"invalid_{label}"))
                    continue
                if email.lower() not in dedup:
                    dedup[email.lower()] = None

        add_many(to, "to")
        add_many(cc, "cc")
        add_many(bcc, "bcc")

        return list(dedup.keys()), skipped

    def _build_message(self, subject: str, plain: str, html: Optional[str], reply_to: Optional[str]) -> MIMEMultipart | MIMEText:
        sender = self.email_config["sender"]
        if html:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = sender
            msg["To"] = ""  # filled per batch
            if reply_to:
                msg.add_header("Reply-To", reply_to)
            msg.attach(MIMEText(plain or "", "plain", "utf-8"))
            msg.attach(MIMEText(html, "html", "utf-8"))
            return msg
        # plain only
        msg = MIMEText(plain or "", "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = ""  # filled per batch
        if reply_to:
            msg.add_header("Reply-To", reply_to)
        return msg

    def _sinks(self, rep: BroadcastReport, tags: Optional[List[str]]) -> None:
        # Notify founder (short message)
        try:
            title = "📢 Deen Alert Broadcast Sent" if rep.status in ("success", "partial") else "❌ Deen Alert Broadcast Failed"
            body = f"{rep.status.upper()} — {rep.subject} | sent={len(rep.recipients_sent)} skipped={len(rep.recipients_skipped)} dry_run={rep.dry_run}"
            self.alert.send(title, body)
        except Exception:
            pass

        # Action logger
        if self.log:
            try:
                decision = "APPROVED" if rep.status == "success" else ("WARN" if rep.status == "partial" else "ERROR")
                self.log.log(
                    action_type="Broadcast",
                    decision=decision,
                    module="deen_alert_broadcast",
                    status="Success" if rep.status != "error" else "Failure",
                    reason=rep.subject,
                    context=rep.to_dict(),
                    meta={"tags": list(tags or [])},
                )
            except Exception:
                pass

        # Mission log sink (optional)
        if self.mission_log_sink:
            try:
                verdict = "halal" if rep.status in ("success", "partial") else "shubha"
                score = 0.08 if rep.status == "success" else (0.25 if rep.status == "partial" else 0.5)
                self.mission_log_sink(
                    {
                        "actor_id": "system:broadcast",
                        "activity": "deen_alert_broadcast",
                        "verdict": verdict,
                        "score": score,
                        "reasons": [f"{rep.status} — {rep.subject}"],
                        "tags": ["broadcast", "alerts", *(tags or [])],
                        "payload": rep.to_dict(),
                    }
                )
            except Exception:
                pass


# -------- Example usage --------
if __name__ == "__main__":
    # from hail.config.email_config import EMAIL_CONFIG
    EMAIL_CONFIG = {
        "sender": "your@email.com",
        "password": "app-password",
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 465,
    }

    logger = ActionLogger(also_print=True) if ActionLogger else None
    b = DeenAlertBroadcast(EMAIL_CONFIG, action_logger=logger)

    print(b.send_broadcast(
        "Test Deen Alert",
        "Assalamualaikum — this is a test.",
        ["valid@example.com", "bad@addr", "valid@example.com"],
        html="<p><b>Assalamualaikum</b> — this is a test.</p>",
        dry_run=True,  # safe default while testing
        tags=["demo"]
    ))
