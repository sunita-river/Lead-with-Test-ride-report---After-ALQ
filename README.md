# Lead with Test Ride daily report

Every day at 08:30 IST, the EC2 Linux server (`linux-server/cron.sh lead`) pulls **every row and column** of the Salesforce report
**"Lead with Test ride report - After ALQ"** (with the report's own filters, except the date range - see below),
counts leads (unique Lead IDs), flags leads not reported before, and emails the team:

- the email body, laid out like a Salesforce report subscription: report name, "Open in Salesforce" button, filters and the report's summary totals (the totals, such as Total Converted, come from Salesforce itself; the script only counts total and new leads)
- `Lead_Test_Ride_<date>.csv`: every row and column of the report, plus a "New lead" column (Yes = not reported before). If the CSV is over `MAX_CSV_MB` (17 MB, `config.py`), it is sent as `Lead_Test_Ride_<date>.zip` instead, to stay under the email size limit

A lead with more than one test drive has one row per test drive, as in Salesforce.
**The reporting period is lead Created Date from the 1st of the current month to today** (IST). The script
sets it on every run in place of the date range saved on the report; all other report filters are kept.
Set `MONTH_TO_DATE = False` in `lead_report/config.py` to use the report's saved date range instead.

## Schedule (EC2 Linux server, since 19-Nov-2026)

Both reports run on the EC2 server from `linux-server/crontab.txt`, in their own queue (`lead`), so no other job can
hold them up. GitHub Actions started its "08:37" runs at about 09:25 IST, so the GitHub schedule was removed; the
workflows are kept only for a manual emergency run when the server is down.

| Time (IST) | What happens |
|---|---|
| 08:30 | `cron.sh lead` and `cron.sh lead-raam` start (one after the other, about 2 min each). Each tries up to 3 times, 5 min apart, and never sends a second email once one has gone out |
| 09:00, 09:30 | Backup starts: they do nothing if today's email was sent (`data/last_sent.txt` / `data/raam_last_sent.txt` = today) |
| after each run | Result email (OK / FAILED with the log) to `NOTIFY_TO`; the history and send date are committed to `sunita-river/.../main` |

Mail goes through the server's relay (Amazon SES) as River QA Automation <qa-automation@rideriver.com>, with
sunita@rideriver.com always in Cc. External recipients must be listed in
`linux-server/mail-relay/approved-external-recipients.txt`, or the relay refuses the email.

## RAAM report (same code, different report)

| | After ALQ (`cron.sh lead`) | RAAM (`cron.sh lead-raam`) |
|---|---|---|
| Salesforce report | "Lead with Test ride report - After ALQ" (`00OS2000005qeL3MAI`) | "Lead with Test ride report - Aft_RAAM" (`00OS20000073fVeMAI`); the RAAM dealer codes are a filter on the report in Salesforce |
| Recipients | `LEAD_TO` in `linux-server/cron.sh` | `EMAIL_TO` in job `sf-lead-raam` of `linux-server/run.sh` |
| Subject | Lead with Test Ride Report – After ALQ | Lead with Test Ride Report – After ALQ (RAAM) |
| Time (IST) | 08:30, backups 09:00 / 09:30 | 08:30, backups 09:00 / 09:30 |
| Lead history / send date | `data/lead_history.csv`, `data/last_sent.txt` | `data/raam_lead_history.csv`, `data/raam_last_sent.txt` |

The RAAM job sets `REPORT_ID`, `EMAIL_SUBJECT` and `HISTORY_FILE`; without them `lead_report/config.py` uses the
After ALQ values. To change recipients: edit the list named above (and the same `EMAIL_TO` in the workflow file, for
the emergency run), then copy the linux-server file to the server. To change RAAM dealers: the Dealer Code filter on
the RAAM report in Salesforce.
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
| `.github/workflows/daily_lead_report.yml` | Manual emergency run on GitHub (After ALQ report); no schedule |
| `.github/workflows/raam_lead_report.yml` | Manual emergency run on GitHub (RAAM report); no schedule |
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
| Add or remove recipients | After ALQ: `LEAD_TO` in `linux-server/cron.sh`; RAAM: `sf-lead-raam` in `linux-server/run.sh`. Copy the file to the server. A new address outside rideriver.com also goes in `mail-relay/approved-external-recipients.txt` |
| Salesforce password changed | Reset the security token in Salesforce, then update `SF_PASSWORD` and `SF_SECURITY_TOKEN`. To stop this happening, add `SF_CONSUMER_KEY` and `SF_CONSUMER_SECRET` from a Connected App (client credentials flow); when set they are used instead of the password |
| Gmail login fails | Create a new Gmail App Password and update `SMTP_PASSWORD` |
| A report column was added or removed | Nothing to do - every column is included. If Lead ID or Created Date is renamed, update `lead_report/config.py` |
| Different period | Set `MONTH_TO_DATE = False` in `lead_report/config.py`, then change the date filter on the report in Salesforce |
| Different report | Change `REPORT_ID` in `lead_report/config.py` |
| Different time or day | Edit the `lead` / `lead-raam` lines in `linux-server/crontab.txt` (Indian time), then install it on the server |
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
