import logging
from datetime import date

import pytest

from lead_report import salesforce
from sf_fakes import FakeSalesforce, describe, page, row

TODAY = date(2026, 10, 6)


def test_all_pages_are_fetched_and_combined():
    sf = FakeSalesforce([
        # page 1 is cut off in the middle of L3's test drives: L3 is dropped and fetched again in full
        page([row("L1"), row("L2", test_drive="2026-10-02"), row("L3", test_drive="2026-10-03")],
             all_data=False, row_count=6),
        page([row("L3", test_drive="2026-10-03"), row("L3", test_drive="2026-10-04"), row("L4")],
             all_data=False, row_count=4),   # later pages count only what is left - ignored
        page([row("L4"), row("L5")], all_data=True),
    ])
    df, info = salesforce.fetch_report(sf, "REPORT", today=TODAY)

    assert df["Lead ID"].tolist() == ["L1", "L2", "L3", "L3", "L4", "L5"]
    assert list(df.columns) == ["Created Date", "Company", "Converted", "Qualified Lead",
                                "Test Drive Created Date", "Lead ID"]
    assert df["Test Drive Created Date"].tolist()[2:4] == [date(2026, 10, 3), date(2026, 10, 4)]
    assert df["Created Date"].iloc[0] == date(2026, 10, 1)
    assert len(sf.runs) == 3 and sf.pages == []
    assert all(r["sortBy"] == [{"sortColumn": "Lead.Id", "sortOrder": "Asc"}] for r in sf.runs)
    assert sf.runs[0]["reportFilters"] == []
    assert sf.runs[1]["reportFilters"] == [{"column": "Lead.Id", "operator": "greaterThan", "value": "L2"}]
    assert sf.runs[2]["reportFilters"] == [{"column": "Lead.Id", "operator": "greaterThan", "value": "L3"}]
    # month-to-date replaces the saved September range on every run
    assert all(r["standardDateFilter"]["startDate"] == "2026-10-01" and
               r["standardDateFilter"]["endDate"] == "2026-10-06" for r in sf.runs)

    assert info.totals == [("Total Records", "6")]
    assert info.period == (date(2026, 10, 1), date(2026, 10, 6)) and info.viewer == "Test User"
    assert info.filters == ["All leads", "Created Date: 1/10/26 - 6/10/26"]


def test_saved_filters_and_logic_are_kept_while_paging():
    saved = [{"column": "Lead.Status", "operator": "equals", "value": "Follow Up"}]
    sf = FakeSalesforce([page([row("L1"), row("L2")], all_data=False, row_count=2),
                         page([row("L2")], all_data=True)], describe(filters=saved, logic="1"))
    salesforce.fetch_report(sf, "REPORT", today=TODAY)
    assert sf.runs[0]["reportFilters"] == saved and sf.runs[0]["reportBooleanFilter"] == "1"
    assert sf.runs[1]["reportFilters"] == saved + [{"column": "Lead.Id", "operator": "greaterThan", "value": "L1"}]
    assert sf.runs[1]["reportBooleanFilter"] == "(1) AND 2"


def test_row_count_mismatch_is_logged(caplog):
    # The code's intent: a mismatch between the report's record count and the rows downloaded
    # is reported as a warning (the run continues).
    sf = FakeSalesforce([page([row("L1"), row("L2")], all_data=True, row_count=3)])
    with caplog.at_level(logging.WARNING, logger="lead_report.salesforce"):
        df, _ = salesforce.fetch_report(sf, "REPORT", today=TODAY)
    assert len(df) == 2
    assert "Report says 3 rows but 2 were downloaded" in caplog.text


def test_matching_row_count_logs_no_warning(caplog):
    sf = FakeSalesforce([page([row("L1"), row("L2")], all_data=True, row_count=2)])
    with caplog.at_level(logging.WARNING, logger="lead_report.salesforce"):
        salesforce.fetch_report(sf, "REPORT", today=TODAY)
    assert "were downloaded" not in caplog.text


def test_a_lead_filling_a_whole_page_fails():
    sf = FakeSalesforce([page([row("L1"), row("L1")], all_data=False, row_count=4)])
    with pytest.raises(SystemExit, match="Lead L1 has over 2,000 rows"):
        salesforce.fetch_report(sf, "REPORT", today=TODAY)


def test_empty_report_fails():
    sf = FakeSalesforce([page([], all_data=True, row_count=0)])
    with pytest.raises(SystemExit, match="Report returned no rows"):
        salesforce.fetch_report(sf, "REPORT", today=TODAY)
