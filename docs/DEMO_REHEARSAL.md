# Golden demo rehearsal

The recorded-first rehearsal is intentionally credential-free. Each run opens a fresh browser
context, replays the edge-positive fixture, switches to the veto fixture, and exercises the
market-closed and provider-failure fallbacks. No network request or order submission is part of
this rehearsal.

Run it from the frontend directory with:

$env:CI = "1"
npm run build
npx playwright test tests/rehearsal.spec.ts

The test emits one ISO-8601 timestamp per run. Five consecutive runs are required before the
recorded demo is considered rehearsed.

Latest rehearsal evidence (UTC, 2026-08-30):

| Run | Timestamp |
| --- | --- |
| 1 | 2026-08-30T05:20:18.452Z |
| 2 | 2026-08-30T05:20:18.958Z |
| 3 | 2026-08-30T05:20:19.342Z |
| 4 | 2026-08-30T05:20:19.722Z |
| 5 | 2026-08-30T05:20:20.122Z |
