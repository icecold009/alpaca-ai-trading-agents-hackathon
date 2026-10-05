# RiskCourt personal workstation

The submitted release remains the credential-free recorded demo. This document
covers the local-first workstation built on the feature branch after submission.
It is intentionally single-user, paper-only, and approval-gated.

## Recreate the Python environment

For Windows x64 with CPython 3.12, create and install from the exact-version
dependency closure:

```powershell
py -3.12 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-lock-win-py312.txt
backend\.venv\Scripts\python.exe -m pip install --no-build-isolation --no-deps -e "backend[dev]"
```

The lock pins the runtime, dev, and setuptools build dependencies by version;
it has no artifact hashes and is not a lock for other platforms or Python
versions. Use the configured package index and refresh this lock when project
dependency declarations change.

## Start locally

Run the backend from the repository root in recorded mode first:

```powershell
$env:RISKCOURT_MODE = "recorded"
backend\.venv\Scripts\python.exe -m uvicorn riskcourt.app:app --app-dir backend\src --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
cd frontend
npm.cmd run dev
```

Open the Vite URL. Recorded mode seeds the local SQLite database at
`.riskcourt\riskcourt.sqlite3`, uses SPY/QQQ as the default watchlist, and does
not require or read broker credentials.

`GET /healthz` reports process liveness. `GET /readyz` reports local database,
provider configuration, and (in paper mode) read-only broker-account
reachability. In paper mode, `entry_ready` also requires the OPRA options feed;
an indicative feed can support research but cannot authorize an entry.

## Personal workflow

1. Open Settings and choose the bounded watchlist.
2. Use Scan now to create durable scan and decision records.
3. Inspect juror forecasts, evidence, hurdle, edge, option legs, and maximum loss.
4. Veto a candidate or prepare an approval. Vetoes cannot create orders.
5. In paper mode, confirm the complete order preview and submit with an idempotency key.
6. Review orders, positions, P&L, exits, and journal notes after restarting locally.

The mutation boundary is explicit: scheduled scans may create decisions, but no
scheduled path submits an order. Every entry or exit submission requires a fresh
state check, approval, explicit confirmation, and idempotency key.

## Paper mode

Use a private, ignored `.env` containing only Alpaca paper credentials and the
official paper endpoint. Set `RISKCOURT_MODE=paper`. The default deterministic
provider needs no provider secret; TypeSafe mode is optional and requires its
configured credentials. A deterministic forecast is identified as simulated
evidence. This workstation implements a two-role mode without a news feed.
Startup rejects live flags and non-official endpoints. Credentials, broker
account IDs, raw order payloads, and provider secrets are not returned by the
API or stored in the workstation database.

## Forecast outcomes and calibration

Paper decisions with complete event contracts persist each forecast's role,
raw probability, confidence stake, provider-quality value, evidence count,
model/prompt versions, configured-prior version, and whether the provider was
simulated. Existing decisions without a complete event contract are not guessed
or backfilled.

List unresolved contracts from the local database:

```powershell
backend\.venv\Scripts\python.exe backend\scripts\resolve_forecast_outcomes.py `
  pending --database .riskcourt\riskcourt.sqlite3
```

Create a UTF-8 CSV with exactly this header and one row per `decision_id`:

```csv
decision_id,observed_at,settlement_price,source_name,source_reference
decision_0123456789abcdef0123,2026-10-01T19:59:30+00:00,672.18,alpaca_sip,spy-close-20261001
```

Use a source observation at or before the saved horizon, within its final five
minutes, and after every forecast. The importer rejects unresolved future
horizons, duplicate or unknown decisions, nonpositive prices, unsafe source
references, and malformed CSV. It derives the realized event from the stored
threshold and condition, hashes and stores the exact CSV bytes in SQLite, and
keeps each resolution immutable. The source label is operator-supplied; RiskCourt
does not independently authenticate the source or fetch settlement data.

```powershell
backend\.venv\Scripts\python.exe backend\scripts\resolve_forecast_outcomes.py `
  resolve --database .riskcourt\riskcourt.sqlite3 --input .\settlements.csv
backend\.venv\Scripts\python.exe backend\scripts\resolve_forecast_outcomes.py `
  report --database .riskcourt\riskcourt.sqlite3
```

Reports group by recorded/paper mode, provider mode, juror, model, prompt,
prior version, and simulated status. Simulated forecasts are excluded unless
`--include-simulated` is requested, and remain in separate groups. A group needs
20 resolved forecasts before scoring. Its 25% chronological holdout needs at
least 5 rows and its training portion at least 10; training outcomes must have
been resolved before the first holdout forecast was produced. Smaller or
overlapping samples show counts without scores. Raw and configured-prior
probabilities are scored separately; no metric changes execution weights or
proves profitability. No real settlement dataset was imported for this work.

## Optional scheduler

The scheduler is disabled unless `--enable` is supplied. It calls only
`POST /api/scans`; it cannot submit orders:

```powershell
backend\.venv\Scripts\python.exe backend\scripts\schedule_personal_scans.py `
  --enable --once --base-url http://127.0.0.1:8000

backend\.venv\Scripts\python.exe backend\scripts\schedule_personal_scans.py `
  --enable --interval-minutes 30 --base-url http://127.0.0.1:8000
```

The scheduler validates a loopback HTTP origin, refuses redirects, caps
timeouts and response size, allows only SPY/QQQ, and serializes scans with a
bounded retry delay. A per-origin SQLite exclusive lock allows one scheduler
per API origin; it is released when the process exits. Ctrl+C or a normal
process stop interrupts retry and interval waits. An in-flight HTTP request
exits within its configured timeout. Keep it bound to localhost and stop it
before changing mode or credentials. It never calls an order route.

For a Windows Task Scheduler task, run
`backend\.venv\Scripts\python.exe` with arguments
`backend\scripts\schedule_personal_scans.py --enable --interval-minutes 30 --base-url http://127.0.0.1:8000`
and set the working directory to the repository root. Start the API first and
run both processes as the same workstation user so they use the same private
state directory. Configure the task to avoid starting a second instance; the
scheduler lock is an additional guard. Each scan is persisted by the API. A
restart begins a fresh scan immediately; missed intervals are not replayed.

## Persistence and recovery

SQLite uses WAL mode, parameterized queries, and transactional schema
migrations. The existing hash-chained JSON
audit files under `.riskcourt\events` remain compatible with the paper-cycle
worker. Import them once into SQLite audit history when needed:

```powershell
backend\.venv\Scripts\python.exe backend\scripts\import_personal_audit.py
```

The database contains local decisions, approvals, orders, positions, and
journal data. Store backups in a private user-profile folder. The backup tool
uses SQLite's online backup API, validates integrity and schema, and refuses to
overwrite an existing backup. On non-Windows systems it also sets owner-only
file permissions; on Windows, keep the backup directory under your private
user profile so it inherits your account ACL.

```powershell
$backupDir = Join-Path $env:LOCALAPPDATA "RiskCourt\backups"
$stamp = [DateTime]::UtcNow.ToString("yyyyMMdd'T'HHmmss'Z'")
$backupPath = Join-Path $backupDir "riskcourt-$stamp.sqlite3"
backend\.venv\Scripts\python.exe backend\scripts\manage_personal_state.py `
  backup --database .riskcourt\riskcourt.sqlite3 --destination $backupPath
backend\.venv\Scripts\python.exe backend\scripts\manage_personal_state.py `
  verify --database $backupPath
```

To restore, stop the local backend first and use a verified backup. Restore
refuses to proceed if SQLite WAL/SHM sidecars remain. `--overwrite` is required
for an existing database and first creates a verified
`*.pre-restore-<UTC>.sqlite3` rollback copy beside it. Verify the restored file
before restarting:

```powershell
backend\.venv\Scripts\python.exe backend\scripts\manage_personal_state.py `
  restore --backup $backupPath --database .riskcourt\riskcourt.sqlite3 --overwrite
backend\.venv\Scripts\python.exe backend\scripts\manage_personal_state.py `
  verify --database .riskcourt\riskcourt.sqlite3
```

The tool never prunes during backup. Preview retention cleanup with a chosen
minimum count; deletion requires `--apply` and only matches timestamped managed
backup names. For example, keep 30 copies:

```powershell
backend\.venv\Scripts\python.exe backend\scripts\manage_personal_state.py `
  prune --directory $backupDir --keep 30
backend\.venv\Scripts\python.exe backend\scripts\manage_personal_state.py `
  prune --directory $backupDir --keep 30 --apply
```

Keep the backup folder private and remove old data according to the workstation
owner's retention policy.

The personal API surface is:

`/api/account/summary`, `/api/portfolio`, `/api/watchlist`, `/api/scans`,
`/api/decisions`, `/api/approvals`, `/api/orders`, `/api/positions`,
`/api/kill-switch`, `/api/journal`, and `/api/audit`.

## Verification

From the repository root, run the full credential-free verifier (including
browser E2E) or use `--skip-e2e` for the non-browser checks:

```powershell
backend\.venv\Scripts\python.exe scripts\verify.py --skip-e2e
backend\.venv\Scripts\python.exe scripts\verify.py
```

The browser suite starts a test-only fake backend with a temporary database and
a local production preview. It does not connect to Alpaca or submit broker
orders. To start the application manually, use the two commands in “Start
locally”:

```powershell
cd frontend
npm.cmd run e2e
```

The hosted/public recorded demo is a separate release contract. Do not point it
at a credentialed personal backend or deploy the personal workstation until the
local acceptance flow has been independently verified.
