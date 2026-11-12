# Lead with Test Ride daily report

Every day at 9:00 AM IST, GitHub Actions pulls **every row and column** of the Salesforce report
**"Lead with Test ride report - After ALQ"** (with the report's own filters, except the date range - see below),
counts leads (unique Lead IDs), flags leads not reported before, and emails the team:

- the email body, laid out like a Salesforce report subscription: report name, "Open in Salesforce" button, filters and the report's summary totals (the totals, such as Total Converted, come from Salesforce itself; the script only counts total and new leads)
- `Lead_Test_Ride_<date>.csv`: every row and column of the report, plus a "New lead" column (Yes = not reported before). If the CSV is over `MAX_CSV_MB` (17 MB, `config.py`), it is sent as `Lead_Test_Ride_<date>.zip` instead, to stay under the email size limit

A lead with more than one test drive has one row per test drive, as in Salesforce.
**The reporting period is lead Created Date from the 1st of the current month to today** (IST). The script
sets it on every run in place of the date range saved on the report; all other report filters are kept.
Set `MONTH_TO_DATE = False` in `lead_report/config.py` to use the report's saved date range instead.

## RAAM report (second workflow, same code)

`.github/workflows/raam_lead_report.yml` sends the same report for the RAAM dealers:

| | After ALQ (`daily_lead_report.yml`) | RAAM (`raam_lead_report.yml`) |
|---|---|---|
| Salesforce report | "Lead with Test ride report - After ALQ" (`00OS2000005qeL3MAI`) | "Lead with Test ride report - Aft_RAAM" (`00OS20000073fVeMAI`); the RAAM dealer codes are a filter on the report in Salesforce |
| Recipients | `EMAIL_TO` secret | shagun@raamgroup.in, gunjeet.singh@raamgroup.in, ajish@rideriver.com, aarsh@rideriver.com, elakaya@rideriver.com (in the workflow file) |
| Subject | Lead with Test Ride Report – After ALQ | Lead with Test Ride Report – After ALQ (RAAM) |
| Time (IST) | 08:37, backup 09:37 | 08:47, backup 09:47 |
| Lead history / send date | `data/lead_history.csv`, `data/last_sent.txt` | `data/raam_lead_history.csv`, `data/raam_last_sent.txt` |

The workflow sets `REPORT_ID`, `EMAIL_SUBJECT` and `HISTORY_FILE`; without them `lead_report/config.py` uses the
After ALQ values, so the original report is unchanged. Both use the same repository secrets. The first RAAM run
records the baseline, so no lead is flagged new that day. To change RAAM recipients or dealers: edit `EMAIL_TO` in
`raam_lead_report.yml`, or the Dealer Code filter on the RAAM report in Salesforce.
Run it locally: `DRY_RUN=true REPORT_ID=00OS20000073fVeMAI HISTORY_FILE=data/raam_lead_history.csv python -m lead_report`.

## Layout

| Path | What it does |
|---|---|
| `lead_report/config.py` | **All settings**: report ID, key column names, email subject, plus credentials from env |
| `lead_report/salesforce.py` | Login and download of every report row and column (pages past the 2,000-row API limit by Lead ID) |
| `lead_report/analysis.py` | Lead counts, daily figures, new-lead flags from the history file |
| `lead_report/outputs.py` | Email HTML and the CSV attachment (zipped only above `MAX_CSV_MB` in `config.py`; the button link is `REPORT_URL`) |
| `lead_report/mailer.py` | Builds and sends the email (retries brief connection drops) |
| `lead_report/main.py` | Runs the steps in order |
| `data/lead_history.csv` | Every Lead ID already reported. Updated only after a successful send, then committed by the workflow |
| `.github/workflows/daily_lead_report.yml` | The schedule (After ALQ report) |
| `.github/workflows/raam_lead_report.yml` | The schedule (RAAM report, see above) |
| `data/raam_lead_history.csv`, `data/raam_last_sent.txt` | RAAM's own history and send date (created by its first run) |

## Run locally

```
pip install -r requirements.txt
copy env.example .env        # then fill in the passwords
python -m lead_report        # builds and emails
python -m pytest             # tests
```

To build without emailing, set `DRY_RUN=true` in `.env`. The files go to `output/` and the history is not changed.
Open `output/Lead_Test_Ride_<date>.html` to preview the email.

## GitHub setup (once)

1. Add these repository secrets under **Settings → Secrets and variables → Actions**:
   `SF_USERNAME`, `SF_PASSWORD`, `SF_SECURITY_TOKEN`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_TO`
   (comma-separated, no spaces needed).
2. **Actions → Daily Lead with Test Ride Report → Run workflow** starts a manual run. "Dry run" is ticked by default.
   Download the files from the run page (**Artifacts → lead-report**).

If a run fails, GitHub emails the repository owner. The failing step's log says why.

## Common changes

| Need | Do this |
|---|---|
| Add or remove recipients | Edit the `EMAIL_TO` secret (and `.env` for local runs) |
| Salesforce password changed | Reset the security token in Salesforce, then update `SF_PASSWORD` and `SF_SECURITY_TOKEN`. To stop this happening, add `SF_CONSUMER_KEY` and `SF_CONSUMER_SECRET` from a Connected App (client credentials flow); when set they are used instead of the password |
| Gmail login fails | Create a new Gmail App Password and update `SMTP_PASSWORD` |
| A report column was added or removed | Nothing to do - every column is included. If Lead ID or Created Date is renamed, update `lead_report/config.py` |
| Different period | Set `MONTH_TO_DATE = False` in `lead_report/config.py`, then change the date filter on the report in Salesforce |
| Different report | Change `REPORT_ID` in `lead_report/config.py` |
| Different time or day | Edit the `cron` line in the workflow. It is in UTC: 09:00 IST = `30 3` |
| Start "new" tracking again | Delete `data/lead_history.csv`. The next run records a baseline, with nothing flagged as new |

To stop password expiry from breaking the run, you can switch to a Salesforce Connected App: set `SF_CONSUMER_KEY`,
`SF_CONSUMER_SECRET` and `SF_DOMAIN=rivermobilityprivatelimited2.my` (see `env.example`).

## Browser login and self-healing locators

The emailed report uses the Salesforce API only (`lead_report/salesforce.py`): no browser and no screen locators.
The Playwright files are a separate browser login that saves a session (`npm run login`, runs
`tests/auth.setup.ts` with `pages/LoginPage.ts`).

Every field and button that login uses (Username, Password, Log In, App Launcher) has backup locators in
`pages/selfHeal.ts`. The usual locator is always tried first, so a normal login behaves exactly as before.
If Salesforce renames one, the first matching backup is used, the console shows a
`[HEAL] <element>: primary ... not found, used backup ...` line, and `output/healed-locators.json` records it.
The login carries on; update that locator in `pages/LoginPage.ts`, then delete the file. Nothing is sent to
any outside service.

## Errors you might see

- **`Missing settings: ...`**: a secret or `.env` value is empty.
- **`INVALID_LOGIN`**: wrong password or security token, or the login is blocked by the profile's IP restrictions.
- **`Email login failed`**: the Gmail App Password was revoked or changed.
- **`ConnectionResetError 10054` while sending (local PC)**: antivirus or a firewall is blocking port 587. Keep `SMTP_PORT=465`.
