"""Lead with Test Ride report: Salesforce -> CSV -> email.

1. Download every row and column of the "Lead with Test ride report - After ALQ" Salesforce report
   (lead Created Date from the 1st of this month to today - config.MONTH_TO_DATE)
2. Count leads (unique Lead IDs)
3. Flag leads not reported before (data/lead_history.csv)
4. Email the report summary (laid out like a Salesforce subscription) with every row as a CSV
   (zipped only if it is too big to email);
   save copies in output/

Run:  python -m lead_report                  builds and emails
      DRY_RUN=true python -m lead_report     builds only (output/), no email, history unchanged
"""
import logging

from . import analysis, mailer, outputs, salesforce
from .config import Settings

log = logging.getLogger("lead_report")


def save_outputs(s: Settings, r: analysis.Report, html: str, filename: str, content: bytes):
    """Local copies of what is emailed (also uploaded as the GitHub run's artifact)."""
    out = s.output_dir
    out.mkdir(parents=True, exist_ok=True)
    stem = outputs.file_stem(r)
    (out / filename).write_bytes(content)
    (out / f"{stem}.html").write_text(html, encoding="utf-8")
    log.info("Saved to %s (open %s.html to preview the email)", out, stem)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    s = Settings.from_env()

    df, info = salesforce.fetch_report(salesforce.connect(s))
    r = analysis.build_report(df, info.period, analysis.load_history())
    filename, content = outputs.attachment(r)
    html = outputs.email_html(r, info, filename)
    save_outputs(s, r, html, filename, content)
    log.info("Attachment %s: %.1f MB", filename, len(content) / 1e6)

    if s.dry_run:
        log.info("DRY_RUN - email not sent, lead history unchanged")
        return
    msg = mailer.build_message(s, html, {filename: content})
    mailer.send(s, msg)
    analysis.save_history(r.history)   # only after a successful send, so next run compares against this one


if __name__ == "__main__":
    main()
