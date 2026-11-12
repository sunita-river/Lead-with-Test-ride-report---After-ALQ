# Lead with Test Ride – Daily Report

Every day at 09:00 IST, GitHub Actions pulls **every row and column** of the Salesforce report **"Lead with Test ride report - After ALQ"**, counts leads, flags leads not reported before and emails the team a summary with the full data as a CSV.

- **Repository:** https://github.com/sunita-river/Lead-with-Test-ride-report---After-ALQ
- **Test cases:** `docs/Lead_Test_Ride_Report_Test_Cases.xlsx` in the repository (42 cases, 33 passed; the rest need a live run)
- **Owner:** Sunita Sahu

---

## Reports and recipients

The same code sends two reports, each from its own GitHub Actions workflow. They keep separate lead histories and do not affect each other.

| Report | Salesforce report | Workflow | Time (IST) | Sent to |
|---|---|---|---|---|
| After ALQ | Lead with Test ride report - After ALQ (`00OS2000005qeL3MAI`) | `daily_lead_report.yml` | 08:37, backup 09:37 | `EMAIL_TO` repository secret |
| RAAM (added 12-Nov-2026) | Lead with Test ride report - Aft_RAAM (`00OS20000073fVeMAI`), filtered to the RAAM dealer codes in Salesforce | `raam_lead_report.yml` | 08:47, backup 09:47 | shagun@raamgroup.in, gunjeet.singh@raamgroup.in, ajish@rideriver.com, aarsh@rideriver.com, elakaya@rideriver.com |

RAAM history: `data/raam_lead_history.csv` and `data/raam_last_sent.txt`. Its first run is the baseline, so no lead is flagged new that day.

---

## What it does

| Part | What it does | Uses a browser? | Output |
|---|---|---|---|
| Daily report (`python -m lead_report`) | Logs in to the Salesforce API, downloads the report with its own filters (period: lead Created Date from the 1st of this month to today, IST), counts unique Lead IDs, flags new leads from `data/lead_history.csv`, emails the summary | No (API only) | Email + `Lead_Test_Ride_<date>.csv` (zipped above 17 MB) |
| Browser login (`npm run login`) | Optional Playwright login that saves a Salesforce session (`playwright/.auth/user.json`) | Yes | Saved session |

### Step by step (daily report)
1. Logs in with the Connected App if `SF_CONSUMER_KEY` / `SF_CONSUMER_SECRET` are set, else username + password + security token.
2. Reads the report's description, sets the month-to-date period, and downloads every row. The Reports API returns at most 2,000 rows per call, so it pages by Lead ID.
3. Counts leads (unique Lead IDs) and flags leads not in the history file.
4. Builds the email (laid out like a Salesforce subscription: name, "Open in Salesforce", filters, totals) and the CSV, saves copies in `output/`.
5. Sends the email, then updates the history file (only after a successful send).

### Safety
- **Dry run:** `DRY_RUN=true` builds everything but sends nothing and leaves the history unchanged.
- **A failed email never updates the history**, so the next run compares against the last report actually sent.

---

## How to run

```
pip install -r requirements.txt
copy env.example .env        then fill in the passwords
python -m lead_report        build and email (DRY_RUN=true in .env: build only)
python -m pytest             offline tests

npm install                  once, for the browser login
npm run login                browser login, saves the session
```

---

## Outputs

| File | What it is |
|---|---|
| `output/Lead_Test_Ride_<date>.csv` (or `.zip`) | Every row and column, plus a "New lead" column |
| `output/Lead_Test_Ride_<date>.html` | Preview of the email |
| `data/lead_history.csv` | Every Lead ID already reported (committed by the workflow) |
| `output/healed-locators.json` | Only when the browser login used a backup locator (see below) |

---

## Self-healing locators

The daily report uses the API only, so it has no screen locators. The browser login (`pages/LoginPage.ts`) does: every element it clicks, fills or waits for has **backup locators** in `pages/selfHeal.ts`.

| Element | Usual locator | Backups (visible elements only) |
|---|---|---|
| Username box | textbox "Username" | `#username`, `input[name="username"]`, label "User name" |
| Log In button | button "Log In to Sandbox" | `#Login`, `input[name="Login"]`, button starting "Log in" |
| Password box | textbox "Password" | `#password`, `input[name="pw"]`, label "Password" |
| App Launcher (login finished) | button "App Launcher" | `button[title="App Launcher"]`, the App Launcher waffle icon |

How it works:
1. The usual locator is always tried first. If it matches, it is used unchanged, so a normal login behaves exactly as before.
2. Only if it matches nothing is the first matching backup used. The console shows one line, e.g. `[HEAL] Log In button: primary getByRole('button', { name: 'Log In to Sandbox' }) not found, used backup 1 locator('#Login:visible')`, and the event (element, old locator, backup, page address, time) is added to `output/healed-locators.json`.
3. If nothing matches in time, the login fails with an error naming the element and every locator tried.

**What to do after a heal:** update that locator in `pages/LoginPage.ts` from `output/healed-locators.json`, then delete the file. **No AI and nothing sent anywhere:** the backups are fixed in the code. The browser login sends no email, so heals are not emailed.

---

## Test coverage

| Area | Cases | Positive | Negative | Edge | Passed |
|---|---|---|---|---|---|
| Lead Report | 29 | 16 | 6 | 7 | 26 |
| Browser Login | 6 | 3 | 2 | 1 | 2 |
| Self-healing | 7 | 4 | 1 | 2 | 5 |
| **Total** | **42** | **23** | **9** | **10** | **33** |

Passed on 05-Nov-2026, offline: the 28 unit tests (`python -m pytest`, Salesforce and email replaced by fakes), `npx playwright test --list`, and Playwright mock pages for the login and self-healing (usual page: no heal; renamed fields and buttons: 4 heals, login completes; clear error when nothing matches). No live Salesforce run and no email.

12-Nov-2026 (RAAM): 31 unit tests passed, including 3 new config tests; dry run against the live RAAM report downloaded 2,211 of 2,211 rows (2,205 leads, 1-12 Nov) with the Dealer Code filter shown in the email. No email sent. The first scheduled RAAM send (LTR-29) is still to be confirmed.

---

## Troubleshooting

| Message | What to do |
|---|---|
| `Missing settings: ...` | A secret or `.env` value is empty |
| `INVALID_LOGIN` | Wrong password or security token, or the profile's IP restrictions block the login |
| `Email login failed` | The Gmail App Password was revoked or changed; create a new one |
| `[HEAL] ...: primary ... not found, used backup ...` | Salesforce changed the login page; the login carried on. Fix the locator named in `output/healed-locators.json` |
| `"<element>" not found on the page - tried ...` | The login page changed beyond the backups. Run `npm run login`, find the element and update `pages/LoginPage.ts` |
