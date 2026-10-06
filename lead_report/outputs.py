"""What the team receives: an email laid out like Salesforce's report subscription, and every row as a CSV."""
import io
import zipfile
from datetime import date
from html import escape

import pandas as pd

from . import config
from .analysis import Report
from .salesforce import ReportInfo, short_date

NEW_COLUMN = "New lead"                 # extra CSV column: "Yes" for leads not reported before
# Salesforce subscription email colours
BAR, TITLE, MUTED, NAVY, BUTTON, CHIP_BORDER, PAGE = "#00A1E0", "#080707", "#54698D", "#16325C", "#0070D2", "#D8DDE6", "#F3F4F7"
FONT = "font-family:'Salesforce Sans',Arial,Helvetica,sans-serif"


def file_stem(r: Report) -> str:
    return f"Lead_Test_Ride_{r.today:%Y-%m-%d}"


def _text(v) -> str:
    if v is None or (not isinstance(v, (list, dict)) and pd.isna(v)):
        return ""
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, date):
        return f"{v:%d %b %Y}"
    if isinstance(v, float) and v.is_integer():
        return f"{v:.0f}"
    return str(v)


# ---------------- Email body ----------------
def email_html(r: Report, info: ReportInfo, attachment_name: str, run_at: pd.Timestamp | None = None) -> str:
    run_at = run_at or pd.Timestamp.now(tz=config.TIMEZONE)
    as_of = f"As of {short_date(run_at)} at {run_at:%I:%M %p}".replace(" at 0", " at ")
    subtitle = " · ".join([as_of] + ([f"Viewing as {escape(info.viewer)}"] if info.viewer else []))
    # inline-blocks (not table cells) so chips and totals wrap onto the next line in a narrow window
    chips = "".join(
        f'<div style="display:inline-block;border:1px solid {CHIP_BORDER};border-radius:4px;margin:0 8px 8px 0;'
        f'padding:12px 11px;font-size:14px;color:{NAVY}">{escape(f)}</div>'
        for f in info.filters)
    totals = "".join(
        f'<div style="display:inline-block;vertical-align:top;margin:0 24px 16px 0">'
        f'<div style="font-size:15px;color:{TITLE}">{escape(label)}</div>'
        f'<div style="font-size:26px;color:{NAVY};margin-top:4px">{escape(value)}</div></div>'
        for label, value in info.totals)
    heading = f'font-size:20px;color:{NAVY};font-weight:400;margin:28px 0 12px'
    return f"""<html><body style="margin:0;background:{PAGE};{FONT}">
<table width="100%" cellspacing="0" cellpadding="0" style="background:{PAGE};table-layout:fixed"><tr><td align="center" style="padding:16px 8px">
<table width="100%" cellspacing="0" cellpadding="0" style="max-width:900px;width:100%;background:#FFFFFF;border-top:6px solid {BAR}">
<tr><td style="padding:20px 20px 24px;word-wrap:break-word">
  <div style="text-align:center;font-size:28px;color:{TITLE}">{escape(info.name)}</div>
  <div style="text-align:center;font-size:16px;color:{MUTED};margin-top:10px">{subtitle}</div>
  <div style="text-align:center;margin-top:12px">
    <a href="{escape(config.REPORT_URL)}" style="display:inline-block;background:{BUTTON};color:#FFFFFF;text-decoration:none;
       font-size:15px;padding:14px 20px;border-radius:4px;text-transform:uppercase">OPEN IN SALESFORCE</a></div>

  <div style="{heading}">Details</div>
  <div style="font-size:16px;color:{TITLE};margin-bottom:12px">Filters</div>
  <div>{chips}</div>

  <div style="{heading};margin-top:32px">Summary</div>
  <div>{totals}</div>

  <div style="font-size:14px;color:{MUTED};margin-top:24px;border-top:1px solid {CHIP_BORDER};padding-top:16px">
    &#128206; Attached: <b style="color:{NAVY}">{escape(attachment_name)}</b> – every row and column of the report{
    " (CSV, zipped to fit the email size limit)" if attachment_name.endswith(".zip") else ""}
    ({len(r.rows):,} rows). Column "{NEW_COLUMN}" = Yes marks {r.new_count:,} lead{"" if r.new_count == 1 else "s"} not in earlier emails.</div>
</td></tr></table>
</td></tr></table>
</body></html>"""


# ---------------- CSV ----------------
def csv_bytes(r: Report) -> bytes:
    """Every report row and column, plus "New lead". UTF-8 with BOM so Excel shows names correctly."""
    rows = r.rows.drop(columns="is_new").copy()
    for c in rows.columns:
        rows[c] = rows[c].map(lambda v: f"{v:%Y-%m-%d}" if isinstance(v, date) else _text(v))
    rows.insert(0, NEW_COLUMN, r.rows["is_new"].map({True: "Yes", False: ""}))
    return rows.to_csv(index=False).encode("utf-8-sig")


def attachment(r: Report, max_csv_mb: float = config.MAX_CSV_MB) -> tuple[str, bytes]:
    """(file name, content): the CSV as is, or zipped if it is too big to email."""
    csv = csv_bytes(r)
    if len(csv) <= max_csv_mb * 1e6:
        return f"{file_stem(r)}.csv", csv
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr(f"{file_stem(r)}.csv", csv)
    return f"{file_stem(r)}.zip", buf.getvalue()
