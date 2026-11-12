"""One codebase, two reports: the RAAM workflow picks its report, subject and history file from env."""
import importlib

import pytest

from lead_report import config

OVERRIDES = ("REPORT_ID", "EMAIL_SUBJECT", "HISTORY_FILE")


@pytest.fixture
def reload_config(monkeypatch):
    """Reload config with the test's env, then restore the default settings for the other tests."""
    for name in OVERRIDES:
        monkeypatch.delenv(name, raising=False)
    yield lambda: importlib.reload(config)
    for name in OVERRIDES:
        monkeypatch.delenv(name, raising=False)
    importlib.reload(config)


def test_defaults_are_the_after_alq_report(reload_config):
    c = reload_config()
    assert c.REPORT_ID == "00OS2000005qeL3MAI"
    assert c.REPORT_URL.endswith("/Report/00OS2000005qeL3MAI/view?queryScope=userFolders")
    assert c.EMAIL_SUBJECT == "Lead with Test Ride Report – After ALQ"
    assert c.HISTORY_FILE == c.ROOT / "data" / "lead_history.csv"


def test_raam_workflow_settings(reload_config, monkeypatch):
    monkeypatch.setenv("REPORT_ID", "00OS20000073fVeMAI")
    monkeypatch.setenv("EMAIL_SUBJECT", "Lead with Test Ride Report – After ALQ (RAAM)")
    monkeypatch.setenv("HISTORY_FILE", "data/raam_lead_history.csv")
    c = reload_config()
    assert c.REPORT_ID == "00OS20000073fVeMAI"
    assert c.REPORT_URL == ("https://rivermobilityprivatelimited2.lightning.force.com/lightning/r/Report/"
                            "00OS20000073fVeMAI/view?queryScope=userFolders")
    assert c.EMAIL_SUBJECT.endswith("(RAAM)")
    assert c.HISTORY_FILE == c.ROOT / "data" / "raam_lead_history.csv"


def test_blank_env_keeps_defaults(reload_config, monkeypatch):
    for name in OVERRIDES:
        monkeypatch.setenv(name, "  ")
    c = reload_config()
    assert c.REPORT_ID == "00OS2000005qeL3MAI" and c.HISTORY_FILE.name == "lead_history.csv"
