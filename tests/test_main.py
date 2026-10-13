import functools
import io
import smtplib
from unittest.mock import MagicMock

import pandas as pd
import pytest

from lead_report import analysis, config, main, salesforce
from sf_fakes import FakeSalesforce, page, row

LEAD = "Lead ID"
TODAY = pd.Timestamp("2026-10-05")


def snapshot(*folders):
    """Name, size and mtime of every file in the project's real data/output/logs folders."""
    return {p: (p.stat().st_size, p.stat().st_mtime_ns) for f in folders if f.exists() for p in f.rglob("*")}


@pytest.fixture
def run(fake_env, monkeypatch, tmp_path):
    """Patch Salesforce, SMTP, the history file and the date; returns a function that runs main()."""
    sf = FakeSalesforce([
        page([row("L1"), row("L2", test_drive="2026-10-02"), row("L3")], all_data=False, row_count=4),
        page([row("L3"), row("L4", created="2026-10-03", converted=True)], all_data=True),
    ])
    connect = MagicMock(return_value=sf)
    monkeypatch.setattr(salesforce, "connect", connect)

    server = MagicMock()
    smtp_ssl, smtp_plain = MagicMock(return_value=server), MagicMock(return_value=server)
    monkeypatch.setattr(smtplib, "SMTP_SSL", smtp_ssl)
    monkeypatch.setattr(smtplib, "SMTP", smtp_plain)

    history_file = tmp_path / "data" / "lead_history.csv"
    analysis.save_history(pd.DataFrame({LEAD: ["L1"], "First seen": "2026-10-01", "Batch": "baseline"}), history_file)
    load, save = analysis.load_history, analysis.save_history
    monkeypatch.setattr(analysis, "load_history", lambda: load(history_file))
    monkeypatch.setattr(analysis, "save_history", lambda h: save(h, history_file))
    monkeypatch.setattr(analysis, "build_report", functools.partial(analysis.build_report, today=TODAY))

    real = snapshot(config.ROOT / "data", config.ROOT / "output", config.ROOT / "logs")

    def go(dry_run):
        fake_env("DRY_RUN", "true" if dry_run else "false")
        main.main()
        assert snapshot(config.ROOT / "data", config.ROOT / "output", config.ROOT / "logs") == real
        return dict(sf=sf, connect=connect, smtp_ssl=smtp_ssl, smtp_plain=smtp_plain, server=server,
                    history_file=history_file, output=tmp_path / "output")
    return go


def test_dry_run_builds_outputs_but_sends_nothing(run):
    r = run(dry_run=True)
    assert r["connect"].call_count == 1 and len(r["sf"].runs) == 2   # both pages fetched
    r["smtp_ssl"].assert_not_called()
    r["smtp_plain"].assert_not_called()
    r["server"].send_message.assert_not_called()

    assert sorted(p.name for p in r["output"].iterdir()) == [
        "Lead_Test_Ride_2026-10-05.csv", "Lead_Test_Ride_2026-10-05.html"]
    csv = pd.read_csv(r["output"] / "Lead_Test_Ride_2026-10-05.csv", encoding="utf-8-sig", dtype=str,
                      keep_default_na=False)
    assert sorted(csv[LEAD]) == ["L1", "L2", "L3", "L4"]
    assert dict(zip(csv[LEAD], csv["New lead"])) == {"L1": "", "L2": "Yes", "L3": "Yes", "L4": "Yes"}
    html = (r["output"] / "Lead_Test_Ride_2026-10-05.html").read_text(encoding="utf-8")
    assert "Viewing as Test User" in html and ">Total Records</div>" in html
    # dry run leaves the history as it was
    assert pd.read_csv(r["history_file"], dtype=str)[LEAD].tolist() == ["L1"]


def test_real_run_emails_and_then_updates_history(run):
    r = run(dry_run=False)
    r["smtp_ssl"].assert_called_once_with("smtp.gmail.com", 465, timeout=60)
    r["server"].login.assert_called_once_with("sender@example.com", "smtp-pw")
    msg = r["server"].send_message.call_args.args[0]
    assert msg["To"] == "a@example.com, b@example.com"
    (att,) = msg.iter_attachments()
    assert att.get_filename() == "Lead_Test_Ride_2026-10-05.csv"
    emailed = pd.read_csv(io.BytesIO(att.get_payload(decode=True)), encoding="utf-8-sig", dtype=str)
    assert sorted(emailed[LEAD]) == ["L1", "L2", "L3", "L4"]

    history = pd.read_csv(r["history_file"], dtype=str)
    assert sorted(history[LEAD]) == ["L1", "L2", "L3", "L4"]
    assert history.set_index(LEAD).loc["L1", "Batch"] == "baseline"


def test_failed_email_leaves_history_unchanged(run, monkeypatch, tmp_path):
    monkeypatch.setattr(smtplib, "SMTP_SSL", MagicMock(side_effect=OSError("down")))
    monkeypatch.setattr("lead_report.mailer.time.sleep", lambda s: None)
    with pytest.raises(OSError):
        run(dry_run=False)
    assert pd.read_csv(tmp_path / "data" / "lead_history.csv", dtype=str)[LEAD].tolist() == ["L1"]
