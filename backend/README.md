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

For a pinned Windows x64 Python 3.12 setup, run these commands from the
repository root. The lock pins project runtime/dev dependencies and the
setuptools build backend; install it before the editable project because build
isolation is disabled for that final step:

```powershell
py -3.12 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-lock-win-py312.txt
backend\.venv\Scripts\python.exe -m pip install --no-build-isolation --no-deps -e "backend[dev]"
```

The lock is Windows x64 / CPython 3.12 specific and pins versions without
artifact hashes. Resolve dependencies separately on other platforms and
Python versions.

The editable install includes FastAPI, Pydantic settings, SQLAlchemy/Alembic with SQLite support, Alpaca's Python SDK, and the model SDK. The `dev` extra adds the test, lint, type-check, and coverage tools.

## Runtime modes

- `RISKCOURT_MODE=recorded` is the default and starts without credentials or network access.
- `RISKCOURT_MODE=paper` requires both `ALPACA_API_KEY_ID` and `ALPACA_API_SECRET_KEY`.
- `RISKCOURT_AI_MODE=deterministic` is the default; `shadow` records a TypeSafe comparison while
  preserving the deterministic result; `typesafe` requires `TYPESAFE_API_KEY` in paper mode.
- TypeSafe receives only role-scoped market/options/news evidence summaries and timestamps. It
  cannot select strikes, set prices or quantities, bypass a veto, issue approval, or submit an order.
- `TYPESAFE_MIN_EVIDENCE_QUALITY` defaults to `0.60`. A low-quality TypeSafe judgment abstains for
  that role; missing catalyst/news evidence no longer blocks market and volatility jurors.
- TypeSafe metadata records a sanitized state hash, model/question-set versions, primitive
  probabilities, Choice/Score distributions, evidence quality, latency, and token usage for shadow
  calibration. `Noul` probability is not treated as model confidence.
- `ALPACA_PAPER_BASE_URL` must remain `https://paper-api.alpaca.markets`.
- Setting `RISKCOURT_LIVE_TRADING` or `ALPACA_LIVE_TRADING` to `true` aborts startup. RiskCourt has no live-money mode.

The local personal-workstation API uses SQLite under `RISKCOURT_STATE_DIR` and
is documented in [`../docs/PERSONAL_WORKSTATION.md`](../docs/PERSONAL_WORKSTATION.md).
Keep it bound to `127.0.0.1`; its mutation routes are not a hosted public API.

## Paper-cycle operator boundary

`scripts/run_paper_cycle.py` is the only bundled command that can reach the
paper order adapter. It performs a read-only preflight by default:

```powershell
.\.venv\Scripts\python.exe scripts/run_paper_cycle.py --symbol SPY
```

Submission requires an explicit `--submit`. Daily P&L is derived from the broker account snapshot. The command persists
the hash-chained audit log under `RISKCOURT_STATE_DIR/events/`, refuses to reuse
an existing case ID, and prints only sanitized evidence. It never supports live
money or exposes an unauthenticated submission route.

```powershell
.\.venv\Scripts\python.exe scripts/run_paper_cycle.py `
  --submit `
  --case-id case_runner_20260831_120000
```

Use `--provider module:attribute` only when supplying a custom provider in deterministic or shadow
mode. The bundled TypeSafe adapter is selected through `RISKCOURT_AI_MODE` and the server-side
`TYPESAFE_API_KEY`, `TYPESAFE_MODEL`, timeout, call, and cost limits.

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
