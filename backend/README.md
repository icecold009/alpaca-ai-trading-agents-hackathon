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
