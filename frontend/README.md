# Frontend

The React judge interface and its unit, accessibility, and browser tests live here.

The UI will clearly distinguish recorded cases from Alpaca paper activity and show jury probabilities, market-implied hurdles, risk verdicts, orders, and paper P&L.

## Commands

```powershell
npm install
npm run dev
npm run test
npm run lint
npm run typecheck
npm run build
npm run e2e
```

Playwright's Chromium browser must be installed before the full end-to-end command can run. `npm run e2e:list` validates test discovery without downloading a browser.
