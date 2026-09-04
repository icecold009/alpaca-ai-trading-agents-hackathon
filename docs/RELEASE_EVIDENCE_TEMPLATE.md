# Release evidence template

Complete this file only after the hosted app, live paper loop, video, and submission are approved. Keep account IDs, order IDs, deployment tokens, and private screenshots in the private evidence store; use redacted references here.

## Immutable build

- Release branch: `main`
- Candidate commit SHA: `PENDING — record after the final approved main merge`
- Verification command: `backend\\.venv\\Scripts\\python.exe scripts\\verify.py --skip-e2e`
- Local verifier result: `PASS on the current main baseline; rerun after each release change`
- Local hosted-contract emulation: `PASS — recorded frontend/backend; healthz, recorded cases, fail-closed flags, and exact CORS`
- Public repository URL: `https://github.com/icecold009/alpaca-ai-trading-agents-hackathon/tree/main`

## Hosted verification

- Backend platform/region: `Render / Singapore`
- Frontend platform/region: `Render Static Site`
- Backend deployment ID: `PENDING — record the final main deployment`
- Frontend deployment ID: `PENDING — record the final main deployment`
- Public app URL: `https://riskcourt-frontend.onrender.com`
- Health check timestamp/status: `PENDING`
- Incognito desktop recorded-case result: `PENDING`
- Incognito mobile recorded-case result: `PENDING`
- Restart/cold-start result: `PENDING`
- Hosted CORS/headers/log review: `PASS for recorded API and exact frontend origin; complete final manual review`

## Alpaca paper evidence (private linkage)

- Fresh dedicated $100,000 account confirmed: `PENDING`
- Options level confirmed: `PENDING`
- Official Alpaca MCP/CLI evidence: `PENDING`
- Market-open order ID: `PENDING — private only`
- Terminal lifecycle state: `PENDING`
- P&L snapshot timestamp and result: `PENDING — paper performance only`
- Account/order evidence location: `PENDING — private reference only`

## Submission and media

- Video URL/file and duration: `PENDING`
- Captions and secret-redaction check: `PENDING`
- Cover/PDF/deck SHA or upload confirmation: `PENDING`
- LabLab submission time and confirmation URL: `PENDING`
- Final independent link/media check: `PENDING`

## Freeze rule

Do not mark the candidate frozen while any required `PENDING` item remains unresolved. Keep account IDs, order IDs, and private screenshots outside the public repository.
