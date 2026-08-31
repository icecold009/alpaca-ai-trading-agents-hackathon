# Scripts

Cross-platform development, fixture, verification, and release-evidence helpers live here.

Scripts must default to recorded or dry-run behavior and must not place paper orders unless the command explicitly requires paper mode.

- `verify.py` runs the credential-free local unit, build, and secret-scan gate.
- `verify_hosted.py` performs a GET-only public frontend/backend readiness,
  recorded-case, fail-closed, and exact-CORS check.
- `backend/scripts/run_paper_cycle.py` performs a paper read-only preflight by
  default; `--submit` is an explicit, credentialed operator action requiring a
  private provider and known daily P&L.
