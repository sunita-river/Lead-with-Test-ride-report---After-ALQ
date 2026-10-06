import io
import zipfile
from datetime import date

import pandas as pd
import pytest

from lead_report import analysis, config, outputs, salesforce
from lead_report.config import Settings

LEAD = "Lead ID"
TODAY = pd.Timestamp("2026-10-05")
PERIOD = (date(2026, 9, 1), date(2026, 9, 30))
COLUMNS = ["Created Date", "Company", "Phone", "Lead Status", "Store Name", "City", "Converted", "Qualified Lead",
           "Test Drive Created Date", "Test Drive Status", LEAD]

SAMPLE = pd.DataFrame([
    (date(2026, 9, 1), "Acme", "91", "Follow Up", "Store A", "Pune", False, False, None, None, "L1"),
    (date(2026, 9, 2), "Lake, View", "92", "Test Ride", "Store B", "Pune", True, True, date(2026, 9, 3), "Completed", "L2"),
    (date(2026, 9, 2), "Lake, View", "92", "Test Ride", "Store B", "Pune", True, True, date(2026, 9, 9), "Scheduled", "L2"),
    (date(2026, 9, 4), "Third", "93", "Converted", None, "Delhi", True, False, None, None, "L3"),
], columns=COLUMNS)


def history(*ids, first_seen="2026-09-28", batch="baseline"):
    return pd.DataFrame({LEAD: list(ids), "First seen": first_seen, "Batch": batch})


def test_every_row_kept_and_leads_counted_once():
    r = analysis.build_report(SAMPLE, PERIOD, history("L1", "L2", "L3"), today=TODAY)
    assert len(r.rows) == 4 and r.total == 3
    assert list(r.rows.columns) == COLUMNS + ["is_new"]
    assert r.period == "01 Sep 2026 - 30 Sep 2026"


def test_period_falls_back_to_the_data_without_a_report_filter():
    r = analysis.build_report(SAMPLE, None, None, today=TODAY)
    assert (r.start, r.end) == (pd.Timestamp("2026-09-01"), pd.Timestamp("2026-09-04"))


def test_first_run_is_baseline_with_nothing_new():
    r = analysis.build_report(SAMPLE, PERIOD, None, today=TODAY)
    assert r.new_count == 0 and r.prev_run is None
    assert list(r.history[LEAD]) == ["L3", "L2", "L1"] and set(r.history["Batch"]) == {"baseline"}


def test_unseen_leads_are_new_and_added_to_history_once():
    r = analysis.build_report(SAMPLE, PERIOD, history("L1", "L3"), today=TODAY)
    assert r.new_count == 1 and len(r.new_rows) == 2            # both of L2's test drives are highlighted
    assert r.new_label == "New since 28 Sep"
    assert r.history.iloc[-1].tolist() == ["L2", "2026-10-05", "update"] and len(r.history) == 3


def test_rerun_on_same_day_keeps_todays_new_leads_flagged():
    first = analysis.build_report(SAMPLE, PERIOD, history("L1", "L3"), today=TODAY)
    again = analysis.build_report(SAMPLE, PERIOD, first.history, today=TODAY)
    assert again.new_count == 1 and len(again.history) == len(first.history)


def test_duplicate_report_labels_are_made_unique():
    meta = {"detailColumns": ["Lead.CreatedDate", "Test_Drive__c.CreatedDate", "Lead.City", "Lead.City__c"]}
    info = {"Lead.CreatedDate": {"label": "Created Date"}, "Test_Drive__c.CreatedDate": {"label": "Created Date"},
            "Lead.City": {"label": "City"}, "Lead.City__c": {"label": "City"}}
    assert salesforce._labels(meta, info) == ["Created Date", "Test Drive Created Date", "City", "City (City__c)"]


def test_summary_and_filters_read_like_salesforce():
    describe = {
        "reportMetadata": {"aggregates": ["s!Lead.IsConverted", "RowCount"], "scope": "organization",
                           "standardDateFilter": {"column": "Lead.CreatedDate", "startDate": "2026-10-01", "endDate": "2026-10-05"},
                           "reportFilters": [{"column": "Lead.Status", "operator": "equals", "value": "Follow Up"}]},
        "reportExtendedMetadata": {"aggregateColumnInfo": {"s!Lead.IsConverted": {"label": "Sum of Converted"},
                                                           "RowCount": {"label": "Record Count"}}},
        "reportTypeMetadata": {"categories": [{"columns": {"Lead.CreatedDate": {"label": "Created Date"},
                                                           "Lead.Status": {"label": "Lead Status"}}}],
                               "scopeInfo": {"values": [{"value": "organization", "label": "All leads"}]}},
    }
    assert salesforce._filters(describe) == ["All leads", "Created Date: 1/10/26 - 5/10/26", "Lead Status equals Follow Up"]
    assert salesforce._totals(describe, [{"label": "1,142"}, {"label": "6,151"}]) == [
        ("Total Records", "6,151"), ("Total Converted", "1,142")]


def test_month_to_date_filter_replaces_the_saved_range():
    assert salesforce.month_to_date(date(2026, 10, 6)) == (date(2026, 10, 1), date(2026, 10, 6))
    assert salesforce.month_to_date(date(2026, 11, 1)) == (date(2026, 11, 1), date(2026, 11, 1))
    meta = {"standardDateFilter": {"column": "Lead.CreatedDate", "durationValue": "CUSTOM",
                                   "startDate": "2026-09-01", "endDate": "2026-09-30"}}
    salesforce._set_month_to_date(meta, date(2026, 10, 6))
    assert salesforce._period(meta) == (date(2026, 10, 1), date(2026, 10, 6))


def test_cells_use_the_ist_date_label_and_blank_dashes():
    assert salesforce._cell({"value": "2026-08-31", "label": "01/09/2026"}, "date") == date(2026, 9, 1)
    assert salesforce._cell({"value": None, "label": "-"}, "string") is None
    assert salesforce._cell({"value": False, "label": "false"}, "boolean") is False
    assert salesforce._cell({"value": "005X", "label": "Jishena"}, "string") == "Jishena"


def test_outputs_render():
    r = analysis.build_report(SAMPLE, PERIOD, history("L1", "L3"), today=TODAY)
    csv = pd.read_csv(io.BytesIO(outputs.csv_bytes(r)), encoding="utf-8-sig", dtype=str, keep_default_na=False)
    assert list(csv.columns) == ["New lead"] + COLUMNS                   # every report column
    assert list(csv["New lead"]) == ["", "Yes", "Yes", ""] and list(csv[LEAD]) == ["L3", "L2", "L2", "L1"]
    assert csv.iloc[3].tolist() == ["", "2026-09-01", "Acme", "91", "Follow Up", "Store A", "Pune", "No", "No", "", "", "L1"]

    info = salesforce.ReportInfo(name="Lead with Test ride report - After ALQ", period=PERIOD,
                                 filters=["All leads", "Created Date: 1/9/26 - 30/9/26"],
                                 totals=[("Total Records", "4"), ("Total Converted", "3")], viewer="Sunita Sahu")
    html = outputs.email_html(r, info, "Lead_Test_Ride_2026-10-05.csv", run_at=pd.Timestamp("2026-10-06 09:00"))
    assert "As of 6/10/26 at 9:00 AM · Viewing as Sunita Sahu" in html
    assert config.REPORT_URL in html and "OPEN IN SALESFORCE" in html
    assert ">Created Date: 1/9/26 - 30/9/26</div>" in html and ">Total Converted</div>" in html
    assert "Lead_Test_Ride_2026-10-05.csv" in html and "marks 1 lead not" in html


def test_csv_is_zipped_only_when_too_big_to_email():
    r = analysis.build_report(SAMPLE, PERIOD, None, today=TODAY)
    name, content = outputs.attachment(r)
    assert name == "Lead_Test_Ride_2026-10-05.csv" and content == outputs.csv_bytes(r)

    name, content = outputs.attachment(r, max_csv_mb=0)
    assert name == "Lead_Test_Ride_2026-10-05.zip"
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        assert z.read("Lead_Test_Ride_2026-10-05.csv") == outputs.csv_bytes(r)
    assert "zipped to fit the email size limit" in outputs.email_html(r, salesforce.ReportInfo("R", PERIOD), name)


def test_missing_secrets_are_reported_together(monkeypatch):
    for name in ["SF_USERNAME", "SF_PASSWORD", "SF_SECURITY_TOKEN", "SF_CONSUMER_KEY",
                 "SMTP_USER", "SMTP_PASSWORD", "EMAIL_TO"]:
        monkeypatch.setenv(name, "")
    monkeypatch.setenv("DRY_RUN", "false")
    with pytest.raises(SystemExit, match="SF_USERNAME, SF_PASSWORD, SF_SECURITY_TOKEN, SMTP_USER"):
        Settings.from_env()
