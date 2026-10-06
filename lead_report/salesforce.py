"""Salesforce login and report download."""
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from simple_salesforce import Salesforce
from urllib3.util.retry import Retry

from . import config
from .config import Settings

log = logging.getLogger(__name__)

API_PAGE_LIMIT = 2000   # rows the Reports API returns per call
MAX_PAGES = 500         # safety stop (1,000,000 rows)
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def connect(s: Settings) -> Salesforce:
    """Connected App (client credentials) if configured, else username + password + security token."""
    session = requests.Session()   # retries brief network / server hiccups instead of failing the run
    session.mount("https://", HTTPAdapter(max_retries=Retry(
        total=4, backoff_factor=5, status_forcelist=(500, 502, 503, 504), allowed_methods=None)))
    if s.uses_connected_app:
        log.info("Logging in to Salesforce with Connected App")
        return Salesforce(consumer_key=s.sf_consumer_key, consumer_secret=s.sf_consumer_secret,
                          domain=s.sf_domain, session=session)
    log.info("Logging in to Salesforce as %s", s.sf_username)
    return Salesforce(username=s.sf_username, password=s.sf_password,
                      security_token=s.sf_security_token, domain=s.sf_domain, session=session)


@dataclass
class ReportInfo:
    """What the email shows above the data, as Salesforce shows it."""
    name: str
    period: tuple[date, date] | None                              # the report's date filter
    filters: list[str] = field(default_factory=list)              # e.g. "All leads", "Created Date: 1/9/26 - 30/9/26"
    totals: list[tuple[str, str]] = field(default_factory=list)   # e.g. ("Total Records", "51,252")
    viewer: str = ""                                              # the Salesforce user the report runs as


OPERATORS = {"equals": "equals", "notEqual": "not equal to", "lessThan": "less than", "greaterThan": "greater than",
             "lessOrEqual": "less or equal", "greaterOrEqual": "greater or equal", "contains": "contains",
             "notContain": "does not contain", "startsWith": "starts with", "includes": "includes", "excludes": "excludes"}


def short_date(d: date) -> str:
    """Salesforce's own e-mail format for the user's locale: 1/9/26."""
    return f"{d.day}/{d.month}/{d:%y}"


def _filters(describe: dict) -> list[str]:
    meta = describe["reportMetadata"]
    labels = {k: v["label"] for cat in describe["reportTypeMetadata"]["categories"] for k, v in cat["columns"].items()}
    scopes = {s["value"]: s["label"] for s in (describe["reportTypeMetadata"].get("scopeInfo") or {}).get("values", [])}
    out = [scopes[meta["scope"]]] if meta.get("scope") in scopes else []
    period = _period(meta)
    if period:
        col = labels.get(meta["standardDateFilter"]["column"], "Date")
        out.append(f"{col}: {short_date(period[0])} - {short_date(period[1])}")
    for f in meta.get("reportFilters") or []:
        out.append(f'{labels.get(f["column"], f["column"])} {OPERATORS.get(f["operator"], f["operator"])} {f["value"]}')
    if meta.get("reportBooleanFilter"):
        out.append(f'Filter logic: {meta["reportBooleanFilter"]}')
    return out


def _totals(describe: dict, aggregates: list[dict]) -> list[tuple[str, str]]:
    """The report's summary row: "Record Count" -> "Total Records", "Sum of X" -> "Total X"."""
    info = describe["reportExtendedMetadata"]["aggregateColumnInfo"]
    names = describe["reportMetadata"]["aggregates"]
    out = []
    for name, agg in zip(names, aggregates):
        label = info[name]["label"]
        label = "Total Records" if name == "RowCount" else re.sub(r"^Sum of ", "Total ", label)
        out.append((label, agg["label"]))
    out.sort(key=lambda t: t[0] != "Total Records")   # record count first, as in Salesforce
    return out


def _viewer(sf: Salesforce) -> str:
    try:
        return sf.restful("chatter/users/me")["name"]
    except Exception:   # Chatter off or no access - the line is left out
        return ""


def month_to_date(today: date) -> tuple[date, date]:
    return today.replace(day=1), today


def _set_month_to_date(meta: dict, today: date):
    """Replace the report's date filter with Created Date = 1st of this month .. today (this run only)."""
    start, end = month_to_date(today)
    meta["standardDateFilter"] = {"column": config.DATE_FILTER_FIELD, "durationValue": "CUSTOM",
                                  "startDate": start.isoformat(), "endDate": end.isoformat()}


def _cell(c, data_type: str):
    """Salesforce cell -> Python value. Text is kept as Salesforce shows it; blanks ("-") become None."""
    v, label = c.get("value"), c.get("label")
    if v is None and label in (None, "", "-"):
        return None
    if data_type == "date":
        # The label is the day in the user's time zone (IST); the value can be the UTC day before.
        try:
            return datetime.strptime(label, "%d/%m/%Y").date()
        except (TypeError, ValueError):
            return date.fromisoformat(v[:10]) if isinstance(v, str) and ISO_DATE.match(v) else label
    if isinstance(v, dict) and "amount" in v:
        return v["amount"]                        # currency field
    if isinstance(v, (bool, int, float)):
        return v
    return label


def _labels(meta: dict, info: dict) -> list[str]:
    """Column names, made unique: the report shows e.g. "Created Date" for both the lead and the test drive."""
    labels, seen = [], set()
    for api in meta["detailColumns"]:
        label = info[api]["label"]
        if label in seen:
            label = (f"Test Drive {label}" if api.startswith("Test_Drive__c.")
                     else f"{label} ({api.split('.')[-1]})")
        seen.add(label)
        labels.append(label)
    return labels


def _period(meta: dict) -> tuple[date, date] | None:
    f = meta.get("standardDateFilter") or {}
    if f.get("startDate") and f.get("endDate"):
        return date.fromisoformat(f["startDate"]), date.fromisoformat(f["endDate"])
    return None


def fetch_report(sf: Salesforce, report_id: str = config.REPORT_ID,
                 today: date | None = None) -> tuple[pd.DataFrame, ReportInfo]:
    """Download every row and column of the report, with the saved report's own filters - except the
    date range, which is the 1st of this month to today when config.MONTH_TO_DATE is on.

    Returns the rows and the report's name, filters and summary totals (from the unpaged first call,
    so they match Salesforce).
    The Reports API returns at most 2,000 rows per call, so the report is sorted by Lead ID and re-run
    with an extra filter "Lead ID > last lead seen" until all rows are in. A lead can have several rows
    (one per test drive), so the last lead of each page is fetched again on the next page in full.
    """
    describe = sf.restful(f"analytics/reports/{report_id}/describe")
    meta = describe["reportMetadata"]
    if config.MONTH_TO_DATE:
        _set_month_to_date(meta, today or pd.Timestamp.now(tz=config.TIMEZONE).date())
        log.info("Date filter: %s", _filters(describe)[-1] if _period(meta) else "?")
    info = describe["reportExtendedMetadata"]["detailColumnInfo"]
    columns = _labels(meta, info)
    types = [info[c]["dataType"] for c in meta["detailColumns"]]
    if config.LEAD_ID_COLUMN not in columns:
        raise SystemExit(f"Column '{config.LEAD_ID_COLUMN}' must be in the report - it is used to page through all rows.")
    key_idx = columns.index(config.LEAD_ID_COLUMN)
    key_api = meta["detailColumns"][key_idx]

    base_filters = meta.get("reportFilters") or []
    base_logic = meta.get("reportBooleanFilter")
    run_meta = {**meta, "reportFormat": "TABULAR", "groupingsDown": [], "groupingsAcross": [],
                "sortBy": [{"sortColumn": key_api, "sortOrder": "Asc"}]}

    rows, last_key, expected, totals = [], None, None, []
    for page in range(1, MAX_PAGES + 1):
        filters = list(base_filters)
        logic = base_logic
        if last_key is not None:
            filters.append({"column": key_api, "operator": "greaterThan", "value": last_key})
            if base_logic:
                logic = f"({base_logic}) AND {len(filters)}"
        run_meta["reportFilters"] = filters
        run_meta.pop("reportBooleanFilter", None)
        if logic:
            run_meta["reportBooleanFilter"] = logic

        data = sf.restful(f"analytics/reports/{report_id}", method="POST",
                          params={"includeDetails": "true"},
                          data=json.dumps({"reportMetadata": run_meta}))
        fact = data["factMap"].get("T!T", {})
        page_rows = fact.get("rows", [])
        if page == 1 and fact.get("aggregates"):
            totals = _totals(describe, fact["aggregates"])
            count = next((a["value"] for n, a in zip(meta["aggregates"], fact["aggregates"]) if n == "RowCount"), None)
            expected = int(count) if count is not None else None
        complete = data.get("allData", True) or not page_rows
        if not complete:
            # drop the last lead's rows - its other rows may be on the next page
            last = page_rows[-1]["dataCells"][key_idx]["value"]
            page_rows = [r for r in page_rows if r["dataCells"][key_idx]["value"] != last]
            if not page_rows:
                raise SystemExit(f"Lead {last} has over {API_PAGE_LIMIT:,} rows - cannot page past it.")
            last_key = page_rows[-1]["dataCells"][key_idx]["value"]
        rows.extend([_cell(c, t) for c, t in zip(r["dataCells"], types)] for r in page_rows)
        log.info("Page %d: %d rows (total %d of %s)", page, len(page_rows), len(rows),
                 f"{expected:,}" if expected is not None else "?")
        if complete:
            break

    df = pd.DataFrame(rows, columns=columns)
    log.info("Fetched %d rows from report '%s'", len(df), meta.get("name"))
    if expected is not None and len(df) != expected:
        log.warning("Report says %d rows but %d were downloaded", expected, len(df))
    if df.empty:
        raise SystemExit("Report returned no rows - check the report filters and the user's access.")
    return df, ReportInfo(name=meta.get("name") or "", period=_period(meta), filters=_filters(describe),
                          totals=totals, viewer=_viewer(sf))
