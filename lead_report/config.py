"""Every setting in one place.

Report details are constants below - edit them here if the Salesforce report changes.
Credentials and run options come from environment variables: the .env file locally,
repository secrets on GitHub Actions.
"""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# ---- Salesforce report ----
REPORT_ID = "00OS2000005qeL3MAI"              # "Lead with Test ride report - After ALQ"
REPORT_URL = ("https://rivermobilityprivatelimited2.lightning.force.com/lightning/r/Report/"
              "00OS2000005qeL3MAI/view?queryScope=userFolders")   # "Open in Salesforce" button
# Every column of the saved report is downloaded and emailed, in the report's order.
# Labels used twice in the report get a suffix: the test drive's columns start with "Test Drive ",
# others end with the field name, e.g. "City (City__c)".
LEAD_ID_COLUMN = "Lead ID"                    # used to page past the API's 2,000-row limit and to flag new leads
DATE_COLUMN = "Created Date"                  # lead created date
TEST_DRIVE_DATE_COLUMN = "Test Drive Created Date"   # blank = the lead has no test ride
TEST_DRIVE_STATUS_COLUMN = "Test Drive Status"
LEAD_STATUS_COLUMN = "Lead Status"
CONVERTED_COLUMN = "Converted"
QUALIFIED_COLUMN = "Qualified Lead"
# Reporting period: lead Created Date from the 1st of the current month to today (IST), set on every run
# in place of the saved report's date range. False = use the date range saved on the report in Salesforce.
MONTH_TO_DATE = True
DATE_FILTER_FIELD = "Lead.CreatedDate"      # API name of the lead Created Date column

# ---- Files ----
TIMEZONE = "Asia/Kolkata"
HISTORY_FILE = ROOT / "data" / "lead_history.csv"  # every Lead ID already reported, to flag new ones

# ---- Email ----
EMAIL_SUBJECT = "Lead with Test Ride Report – After ALQ"
# Attach the CSV as is up to this size; above it, attach it zipped. Attachments grow about 37% when
# emailed, so 17 MB of CSV is about 23 MB of email - under Gmail's 25 MB limit.
MAX_CSV_MB = 17


@dataclass(frozen=True)
class Settings:
    sf_username: str
    sf_password: str
    sf_security_token: str
    sf_domain: str
    sf_consumer_key: str
    sf_consumer_secret: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    email_from: str
    email_to: list[str]
    dry_run: bool
    output_dir: Path

    @classmethod
    def from_env(cls) -> "Settings":
        env = lambda name, default="": os.getenv(name, default).strip()
        s = cls(
            sf_username=env("SF_USERNAME"),
            sf_password=env("SF_PASSWORD"),
            sf_security_token=env("SF_SECURITY_TOKEN"),
            sf_domain=env("SF_DOMAIN", "login"),   # "test" = sandbox, or a My Domain such as "acme.my"
            sf_consumer_key=env("SF_CONSUMER_KEY"),
            sf_consumer_secret=env("SF_CONSUMER_SECRET"),
            smtp_host=env("SMTP_HOST", "smtp.gmail.com"),
            smtp_port=int(env("SMTP_PORT", "465")),
            smtp_user=env("SMTP_USER"),
            smtp_password=env("SMTP_PASSWORD"),
            email_from=env("EMAIL_FROM") or env("SMTP_USER"),
            email_to=[e.strip() for e in env("EMAIL_TO").split(",") if e.strip()],
            dry_run=env("DRY_RUN", "false").lower() == "true",
            output_dir=Path(env("OUTPUT_DIR") or ROOT / "output"),
        )
        s._validate()
        return s

    @property
    def uses_connected_app(self) -> bool:
        return bool(self.sf_consumer_key)

    def _validate(self):
        """Fail at start-up with one clear message instead of halfway through the run."""
        if self.uses_connected_app:
            required = {"SF_CONSUMER_SECRET": self.sf_consumer_secret}
        else:
            required = {"SF_USERNAME": self.sf_username, "SF_PASSWORD": self.sf_password,
                        "SF_SECURITY_TOKEN": self.sf_security_token}
        if not self.dry_run:
            required |= {"SMTP_USER": self.smtp_user, "SMTP_PASSWORD": self.smtp_password,
                         "EMAIL_TO": self.email_to}
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise SystemExit(f"Missing settings: {', '.join(missing)} - add them to .env "
                             f"(local) or the repository secrets (GitHub).")
