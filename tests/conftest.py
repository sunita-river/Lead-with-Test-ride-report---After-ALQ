import os
import socket

import pytest

# Tests never read the real .env (secrets). Must be set before lead_report.config is imported.
os.environ["PYTHON_DOTENV_DISABLED"] = "1"

SECRET_NAMES = ["SF_USERNAME", "SF_PASSWORD", "SF_SECURITY_TOKEN", "SF_DOMAIN", "SF_CONSUMER_KEY",
                "SF_CONSUMER_SECRET", "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD",
                "EMAIL_FROM", "EMAIL_TO", "DRY_RUN", "OUTPUT_DIR"]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """No test may reach Salesforce or a mail server: any real connection attempt fails."""
    def refuse(*args, **kwargs):
        raise RuntimeError("Network access is disabled in tests")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture
def fake_env(monkeypatch, tmp_path):
    """Fake credentials and an output folder under tmp_path; returns a setter for overrides."""
    for name in SECRET_NAMES:
        monkeypatch.delenv(name, raising=False)
    values = {"SF_USERNAME": "user@example.com", "SF_PASSWORD": "pw", "SF_SECURITY_TOKEN": "tok",
              "SMTP_USER": "sender@example.com", "SMTP_PASSWORD": "smtp-pw", "SMTP_PORT": "465",
              "EMAIL_TO": "a@example.com, b@example.com", "DRY_RUN": "true",
              "OUTPUT_DIR": str(tmp_path / "output")}
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return lambda name, value: monkeypatch.setenv(name, value)
