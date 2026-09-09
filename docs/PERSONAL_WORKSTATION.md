# RiskCourt personal workstation

The submitted release remains the credential-free recorded demo. This document
covers the local-first workstation built on the feature branch after submission.
It is intentionally single-user, paper-only, and approval-gated.

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
official paper endpoint. Set `RISKCOURT_MODE=paper` and configure the private
provider specification required by the three-juror implementation. Startup
rejects live flags and non-official endpoints. Credentials, broker account IDs,
raw order payloads, and provider secrets are not returned by the API or stored
in the workstation database.

## Optional scheduler

The scheduler is disabled unless `--enable` is supplied. It calls only
`POST /api/scans`; it cannot submit orders:

```powershell
backend\.venv\Scripts\python.exe backend\scripts\schedule_personal_scans.py `
  --enable --once --base-url http://127.0.0.1:8000

backend\.venv\Scripts\python.exe backend\scripts\schedule_personal_scans.py `
  --enable --interval-minutes 30 --base-url http://127.0.0.1:8000
```

Keep the scheduler bound to localhost. Stop it before changing mode or
credentials.

## Persistence and recovery

SQLite uses WAL mode and parameterized queries. The existing hash-chained JSON
audit files under `.riskcourt\events` remain compatible with the paper-cycle
worker. Import them once into SQLite audit history when needed:

```powershell
backend\.venv\Scripts\python.exe backend\scripts\import_personal_audit.py
```

The database is disposable local state; back it up only after checking
that the destination is private and contains no credentials.

The personal API surface is:

`/api/account/summary`, `/api/portfolio`, `/api/watchlist`, `/api/scans`,
`/api/decisions`, `/api/approvals`, `/api/orders`, `/api/positions`,
`/api/kill-switch`, `/api/journal`, and `/api/audit`.

## Verification

From the repository root:

```powershell
backend\.venv\Scripts\python.exe scripts\verify.py --skip-e2e
cd frontend
npm.cmd run e2e
```

The hosted/public recorded demo is a separate release contract. Do not point it
at a credentialed personal backend or deploy the personal workstation until the
local acceptance flow has been independently verified.
