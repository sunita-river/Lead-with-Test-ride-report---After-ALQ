"""Prepare the report rows and flag leads not reported before."""
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from . import config
from .config import CONVERTED_COLUMN, DATE_COLUMN, LEAD_ID_COLUMN, QUALIFIED_COLUMN

log = logging.getLogger(__name__)


@dataclass
class Report:
    today: pd.Timestamp
    start: pd.Timestamp            # the saved report's date filter (or the first lead's date)
    end: pd.Timestamp
    rows: pd.DataFrame             # every report row and column + "is_new", newest lead first
    history: pd.DataFrame          # Lead ID history to save after a successful send
    prev_run: pd.Timestamp | None  # date of the previous update, None on the first run

    @property
    def period(self) -> str:
        return f"{self.start:%d %b %Y} - {self.end:%d %b %Y}"

    @property
    def total(self) -> int:
        return self.rows[LEAD_ID_COLUMN].nunique()

    @property
    def new_rows(self) -> pd.DataFrame:
        return self.rows[self.rows["is_new"]]

    @property
    def new_count(self) -> int:
        return self.new_rows[LEAD_ID_COLUMN].nunique()

    @property
    def new_label(self) -> str:
        return f"New since {self.prev_run:%d %b}" if self.prev_run is not None else "New since last update"


def as_bool(s: pd.Series) -> pd.Series:
    return s.map(lambda v: v if isinstance(v, bool) else str(v).strip().lower() == "true").astype(bool)


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Typed copy of the report rows, newest lead first. Rows without a Lead ID are dropped."""
    df = df.copy()
    df[DATE_COLUMN] = pd.to_datetime(df[DATE_COLUMN], errors="coerce").dt.date
    for c in (CONVERTED_COLUMN, QUALIFIED_COLUMN):
        df[c] = as_bool(df[c])
    df[LEAD_ID_COLUMN] = df[LEAD_ID_COLUMN].astype("string").str.strip()
    df = df[df[LEAD_ID_COLUMN].notna() & (df[LEAD_ID_COLUMN] != "")]
    return df.sort_values([DATE_COLUMN, LEAD_ID_COLUMN], ascending=False, kind="stable").reset_index(drop=True)


def load_history(path: Path = config.HISTORY_FILE) -> pd.DataFrame | None:
    return pd.read_csv(path, dtype=str) if path.exists() else None


def save_history(history: pd.DataFrame, path: Path = config.HISTORY_FILE):
    path.parent.mkdir(parents=True, exist_ok=True)
    history.to_csv(path, index=False)


def build_report(df: pd.DataFrame, period: tuple[date, date] | None, history: pd.DataFrame | None,
                 today: pd.Timestamp | None = None) -> Report:
    """Analyse the report rows and compare them with the Lead ID history.

    history has one row per lead already reported: Lead ID, "First seen" date and Batch ("baseline" for
    the very first run, "update" afterwards). With no history, every current lead becomes the baseline
    and nothing is flagged new. Re-running on the same day keeps that day's new leads flagged.
    """
    today = today or pd.Timestamp.now(tz=config.TIMEZONE).tz_localize(None).normalize()
    rows = prepare(df)
    if period:
        start, end = map(pd.Timestamp, period)
    else:
        dates = pd.to_datetime(rows[DATE_COLUMN])
        start, end = dates.min(), dates.max()
    today_str = f"{today:%Y-%m-%d}"
    ids = rows[LEAD_ID_COLUMN]
    unique_ids = ids.drop_duplicates()

    if history is None:
        history = pd.DataFrame({LEAD_ID_COLUMN: unique_ids, "First seen": today_str, "Batch": "baseline"})
        log.info("No lead history yet - %d leads become the baseline", len(history))

    added_today = history.loc[(history["First seen"] == today_str) & (history["Batch"] == "update"), LEAD_ID_COLUMN]
    rows["is_new"] = ~ids.isin(history[LEAD_ID_COLUMN]) | ids.isin(added_today)
    unseen = unique_ids[~unique_ids.isin(history[LEAD_ID_COLUMN])]
    updated_history = pd.concat(
        [history, pd.DataFrame({LEAD_ID_COLUMN: unseen, "First seen": today_str, "Batch": "update"})],
        ignore_index=True)

    earlier = history.loc[history["First seen"] < today_str, "First seen"]
    report = Report(today=today, start=start, end=end, rows=rows, history=updated_history,
                    prev_run=pd.Timestamp(earlier.max()) if len(earlier) else None)
    log.info("%d rows, %d leads (%s); %s: %d", len(rows), report.total, report.period, report.new_label, report.new_count)
    return report
