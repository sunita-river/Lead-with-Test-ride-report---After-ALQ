"""Build and send the email."""
import logging
import smtplib
import time
from email.message import EmailMessage

from . import config
from .config import Settings

log = logging.getLogger(__name__)

def build_message(s: Settings, html: str, attachments: dict[str, bytes]) -> EmailMessage:
    """HTML body plus attachments by file name (.csv or .zip)."""
    msg = EmailMessage()
    msg["Subject"] = config.EMAIL_SUBJECT
    msg["From"] = s.email_from
    msg["To"] = ", ".join(s.email_to)
    msg.set_content("Lead with Test Ride daily report. Please view in an HTML-capable email client.")
    msg.add_alternative(html, subtype="html")
    for filename, content in attachments.items():
        maintype, subtype = ("text", "csv") if filename.endswith(".csv") else ("application", "zip")
        msg.add_attachment(content, maintype=maintype, subtype=subtype, filename=filename)
    return msg


def send(s: Settings, msg: EmailMessage, attempts: int = 3):
    """Port 465 = SSL from the start; any other port = STARTTLS. Retries brief connection drops."""
    for attempt in range(1, attempts + 1):
        try:
            if s.smtp_port == 465:
                server = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=60)
            else:
                server = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=60)
            with server:
                if s.smtp_port != 465:
                    server.starttls()
                server.login(s.smtp_user, s.smtp_password)
                server.send_message(msg)
            log.info("Email sent to %s", ", ".join(s.email_to))
            return
        except smtplib.SMTPAuthenticationError:
            raise SystemExit("Email login failed - check SMTP_USER / SMTP_PASSWORD (Gmail needs an App Password).")
        except (OSError, smtplib.SMTPServerDisconnected) as e:
            if attempt == attempts:
                raise
            log.warning("Email attempt %d failed (%s) - retrying in 30 s", attempt, e)
            time.sleep(30)
