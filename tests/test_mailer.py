import smtplib
from unittest.mock import MagicMock

import pytest

from lead_report import config, mailer
from lead_report.config import Settings


@pytest.fixture
def settings(fake_env):
    fake_env("DRY_RUN", "false")
    return Settings.from_env()


@pytest.fixture
def smtp(monkeypatch):
    """Mock SMTP_SSL / SMTP classes and time.sleep; returns (ssl_cls, plain_cls, server, sleep)."""
    server = MagicMock()
    ssl_cls, plain_cls = MagicMock(return_value=server), MagicMock(return_value=server)
    sleep = MagicMock()
    monkeypatch.setattr(smtplib, "SMTP_SSL", ssl_cls)
    monkeypatch.setattr(smtplib, "SMTP", plain_cls)
    monkeypatch.setattr(mailer.time, "sleep", sleep)
    return ssl_cls, plain_cls, server, sleep


def message(s, name="Lead_Test_Ride_2026-10-05.csv", content=b"Lead ID\r\nL1\r\n"):
    return mailer.build_message(s, "<html><b>Report</b></html>", {name: content})


def test_message_has_recipients_html_and_csv(settings):
    msg = message(settings)
    assert msg["To"] == "a@example.com, b@example.com"
    assert msg["From"] == "sender@example.com" and msg["Subject"] == config.EMAIL_SUBJECT
    assert "<b>Report</b>" in msg.get_body(("html",)).get_content()
    (att,) = msg.iter_attachments()
    assert att.get_filename() == "Lead_Test_Ride_2026-10-05.csv" and att.get_content_type() == "text/csv"
    assert att.get_payload(decode=True) == b"Lead ID\r\nL1\r\n"


def test_zip_attachment_type(settings):
    msg = message(settings, "Lead_Test_Ride_2026-10-05.zip", b"PK\x03\x04zip")
    (att,) = msg.iter_attachments()
    assert att.get_content_type() == "application/zip" and att.get_content() == b"PK\x03\x04zip"


def test_send_over_ssl_port_465(settings, smtp):
    ssl_cls, plain_cls, server, sleep = smtp
    msg = message(settings)
    mailer.send(settings, msg)
    ssl_cls.assert_called_once_with("smtp.gmail.com", 465, timeout=60)
    plain_cls.assert_not_called()
    server.starttls.assert_not_called()
    server.login.assert_called_once_with("sender@example.com", "smtp-pw")
    server.send_message.assert_called_once_with(msg)
    sleep.assert_not_called()


def test_send_uses_starttls_on_other_ports(fake_env, smtp):
    fake_env("DRY_RUN", "false")
    fake_env("SMTP_PORT", "587")
    fake_env("SMTP_HOST", "smtp.example.com")
    s = Settings.from_env()
    ssl_cls, plain_cls, server, _ = smtp
    mailer.send(s, message(s))
    plain_cls.assert_called_once_with("smtp.example.com", 587, timeout=60)
    ssl_cls.assert_not_called()
    server.starttls.assert_called_once_with()
    server.send_message.assert_called_once()


def test_send_retries_a_dropped_connection(settings, smtp):
    ssl_cls, _, server, sleep = smtp
    ssl_cls.side_effect = [ConnectionResetError("reset"), smtplib.SMTPServerDisconnected("gone"), server]
    mailer.send(settings, message(settings))
    assert ssl_cls.call_count == 3
    assert sleep.call_count == 2 and sleep.call_args.args == (30,)
    server.send_message.assert_called_once()


def test_send_gives_up_after_the_last_attempt(settings, smtp):
    ssl_cls, _, server, sleep = smtp
    ssl_cls.side_effect = TimeoutError("timed out")
    with pytest.raises(TimeoutError):
        mailer.send(settings, message(settings), attempts=3)
    assert ssl_cls.call_count == 3 and sleep.call_count == 2
    server.send_message.assert_not_called()


def test_wrong_password_fails_at_once_without_retrying(settings, smtp):
    ssl_cls, _, server, sleep = smtp
    server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"bad credentials")
    with pytest.raises(SystemExit, match="Email login failed"):
        mailer.send(settings, message(settings))
    assert ssl_cls.call_count == 1
    sleep.assert_not_called()
    server.send_message.assert_not_called()
