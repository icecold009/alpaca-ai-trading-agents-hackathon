# Backend

FastAPI services, deterministic strategy and risk logic, Alpaca paper-trading adapters, persistence, and backend tests live here.

The backend must support credential-free recorded mode and paper-only Alpaca mode. It must never expose a live-money trading path.

## Tooling

From this directory with Python 3.12 or newer:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m mypy src tests
```

The editable install includes FastAPI, Pydantic settings, SQLAlchemy/Alembic with SQLite support, Alpaca's Python SDK, and the model SDK. The `dev` extra adds the test, lint, type-check, and coverage tools.

## Runtime modes

- `RISKCOURT_MODE=recorded` is the default and starts without credentials or network access.
- `RISKCOURT_MODE=paper` requires both `ALPACA_API_KEY_ID` and `ALPACA_API_SECRET_KEY`.
- `ALPACA_PAPER_BASE_URL` must remain `https://paper-api.alpaca.markets`.
- Setting `RISKCOURT_LIVE_TRADING` or `ALPACA_LIVE_TRADING` to `true` aborts startup. RiskCourt has no live-money mode.

## Paper-cycle operator boundary

`scripts/run_paper_cycle.py` is the only bundled command that can reach the
paper order adapter. It performs a read-only preflight by default:

```powershell
.\.venv\Scripts\python.exe scripts/run_paper_cycle.py --symbol SPY
```

Submission requires an explicit `--submit`, a private provider factory in
`module:attribute` form, and a known `--daily-pnl` value. The command persists
the hash-chained audit log under `RISKCOURT_STATE_DIR/events/`, refuses to reuse
an existing case ID, and prints only sanitized evidence. It never supports live
money or exposes an unauthenticated submission route.

```powershell
.\.venv\Scripts\python.exe scripts/run_paper_cycle.py `
  --submit --provider your_private_provider:build_client `
  --daily-pnl 0 --case-id case_runner_20260831_120000
```

Run the hosted read-only contract checker from the repository root after a
backend and frontend deployment:

```powershell
backend\.venv\Scripts\python.exe scripts/verify_hosted.py `
  --frontend-url https://your-public-frontend.example `
  --backend-url https://your-public-backend.example
```

It issues only GET requests and checks frontend reachability, `/healthz`, the
recorded-case API, recorded fallback/live-trading flags, and the exact CORS
allowlist. A failure is a release blocker.
