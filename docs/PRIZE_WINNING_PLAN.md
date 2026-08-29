# Alpaca AI Trading Agents Hackathon — Revised Prize Plan

**Project:** RiskCourt

**New positioning:** An AI prediction market for options alpha

**Official cutoff:** September 4, 2026 at 8:30 PM IST

**Execution constraint:** Five focused build days plus submission buffer

**Mode:** New $100,000 Alpaca paper account only

> A prize cannot be guaranteed. This revision optimizes for the actual published requirements and the current competitive field.

Use [EVENT_REQUIREMENTS.md](./EVENT_REQUIREMENTS.md) for verified rules and [FIVE_DAY_TODO.md](./FIVE_DAY_TODO.md) for the authoritative execution checklist.

## 1. Why the original plan changed

The live event page introduced requirements that invalidate the equities-only version:

- Options trading is mandatory.
- P&L is an explicit judging criterion.
- Final judging requires a fresh, dedicated Alpaca paper account starting at $100,000.
- The app must use Trading API plus MCP or CLI.
- The submission needs the paper account ID and a one-page AI/risk/infrastructure write-up.

The live field also contains several agents built around debate, risk gates, abstention, spreads, or safe execution. A generic “AI committee plus deterministic risk” story is no longer sufficiently original.

## 2. Revised winning thesis

**RiskCourt is an AI prediction market for options alpha.** Three independent AI jurors analyze price structure, news/catalysts, and option/volatility structure. Each returns a probability forecast and stakes confidence against cited evidence. Deterministic code aggregates and calibrates those beliefs, compares the result with an option-implied break-even probability proxy, and opens a small defined-risk paper options position only when the remaining edge clears a safety margin.

The model never chooses unrestricted order size or bypasses policy. The Decision Card shows:

- Each juror's probability, confidence stake, evidence, and uncertainty.
- Aggregated jury odds.
- Option-implied hurdle and the exact estimated edge.
- Selected option legs, debit, maximum loss, exit rules, and approval state.
- Alpaca order lifecycle and competition paper P&L.

### One-sentence pitch

RiskCourt lets AI agents bet on their forecasts, then trades options only when calibrated jury odds beat market-implied odds by enough to justify the defined risk.

### Memorable demo line

**“The agents do not vote buy or sell. They put probabilities on the record—and the option market cross-examines them.”**

## 3. Strategy definition

### Initial universe

- Underlying: SPY only until the full loop is green; QQQ is optional.
- Expiry: 7–21 calendar days; avoid 0DTE dependence and missing-Greek edge cases.
- Position: one-contract defined-risk vertical debit spread when Level 3 is available.
- Fallback: one long call or long put under Level 2, with the same probability/risk/exit gates.
- Order: day limit order with explicit position intent and deterministic client order ID.

### Decision sequence

1. Fetch paper account, options permissions, positions, pending orders, market clock, underlying bars/quotes, option chain, quotes, IV/Greeks where available, and relevant news.
2. Produce three independent probability forecasts for a precise horizon/outcome.
3. Reject missing evidence, injection, invalid probabilities, stale quotes, or excessive disagreement.
4. Aggregate forecasts using fixed calibration weights.
5. Compute the option-implied break-even hurdle proxy from current executable spread pricing and payoff geometry.
6. Subtract spread/slippage and uncertainty buffers.
7. Abstain unless the remaining probability edge exceeds the configured threshold.
8. Apply deterministic maximum-loss, exposure, daily-drawdown, liquidity, duplicate, freshness, and kill-switch rules.
9. Submit the approved paper options order through Alpaca.
10. Monitor order/position state and exit on fixed profit, loss, edge-decay, time, or kill-switch conditions.
11. Record every transition and paper P&L in a replayable Decision Card.

### Safety envelope

- One contract maximum for the MVP.
- Maximum loss per trade: 0.5% of current paper equity.
- Maximum concurrent options positions: two; begin with one.
- No naked short options.
- No 0DTE dependency.
- No order when quotes are crossed, empty, stale, excessively wide, or unsupported.
- No order when account/options status is uncertain.
- No retry can create a second order.
- No model output can widen a stop, raise maximum loss, enable live trading, or disable the kill switch.

These values are hackathon paper-risk controls, not investment advice.

## 4. Judge strategy

| Criterion | What judges see | Required proof |
|---|---|---|
| P&L Performance | A clear, testable probability-edge strategy, disciplined entries/exits, and current paper P&L from the fresh competition account. | Account-linked order history, P&L timeline, strategy formula, timestamps, and honest simulation caveats. |
| Technology Implementation | Trading API handles option data/execution; MCP or CLI has a meaningful read/verification role; AI jurors produce typed probabilities tied to evidence. | Live/sanitized tool timeline, real paper order, enabled tools, API/CLI transcript, automated tests. |
| Creativity & Originality | The system turns agent disagreement into a calibrated internal prediction market and compares it with option-implied odds. | Jury-vs-market visualization and a case where disagreement correctly causes abstention. |
| Presentation & Execution | The audience understands odds, edge, maximum loss, order, and P&L in under two minutes. | Polished golden demo, recorded fallback, one-page write-up, slides, video, public app. |
| Social Engagement | Transparent build-in-public posts show experiments and setbacks. | Up to five tagged X/LinkedIn links; optional until the release is safe. |

## 5. Architecture

```text
Alpaca account + underlying data + option chain + news
                         |
                         v
               Timestamped Evidence Set
                         |
       +-----------------+-----------------+
       |                 |                 |
 Price Juror       Catalyst Juror    Volatility Juror
       |                 |                 |
       +------- probabilities + stakes ----+
                         |
                         v
       Deterministic Aggregation + Calibration
                         |
        Option-implied hurdle + cost buffers
                         |
                         v
       Edge gate -> abstain OR candidate position
                         |
                         v
        Deterministic Risk and Exit Kernel
                         |
                         v
       Alpaca paper execution and monitoring
                         |
                         v
      Decision Card + audit replay + paper P&L
```

### Recommended implementation

- Frontend: React, TypeScript, Vite, Tailwind, Recharts.
- Backend: Python 3.12, FastAPI, Pydantic, SQLAlchemy/SQLite, `alpaca-py`.
- AI: one structured-output model behind a provider interface with deterministic stubs.
- Alpaca: Trading API for data/execution, MCP for read-only agent research and/or CLI for health/schema/dry-run verification.
- Tests: pytest, Vitest, Playwright, recorded option-chain/order fixtures, 12 adversarial evaluation cases.
- Deployment: accepted public frontend and Python/WebSocket backend platforms; secrets remain server-side.

## 6. Five-day delivery shape

### Day 1 — Eligible offline story

- Scaffold repository and safe modes.
- Freeze formula/data contracts.
- Create recorded edge-positive and abstention cases.
- Deliver clickable jury-odds → option-hurdle → verdict → paper-order/P&L story.

### Day 2 — Probability and risk kernel

- Implement aggregation, hurdle, edge, liquidity, sizing, portfolio, drawdown, duplicate, expiry, exit, and kill-switch rules.
- Implement append-only events and replay.
- Finish adversarial unit coverage before connecting credentials.

### Day 3 — Alpaca options loop

- Verify fresh account, $100,000 balance, and options level.
- Fetch live option chain and build candidates.
- Prove Trading API plus MCP/CLI.
- Place one tiny eligible paper options order and monitor it.

### Day 4 — Autonomous jury and judge UI

- Add independent typed jurors, bounded orchestration, and injection defenses.
- Run 12-case evaluation.
- Finish jury-vs-market view, Decision Card, accessibility, failure states, and five demo rehearsals.

### Day 5 — Release and submission

- Full verification, security/claim review, deployment, one-page write-up, README, cover, video, slides, LabLab copy, optional social posts, freeze, and early submission.

## 7. Golden demo

1. Open a SPY case with visible paper-account and market-data provenance.
2. Show three jurors independently stake probabilities.
3. Reveal the aggregated jury odds beside the option-implied hurdle.
4. Show either:
   - Edge-positive: candidate spread, exact debit/max loss, risk approval, and paper execution.
   - Disagreement/no-edge: visible abstention and zero order.
5. Show the real Alpaca paper order ID/status and current P&L.
6. Replay the Decision Card with every rule and evidence reference.
7. End with the formula and disclaimer, not an unsupported profit claim.

The demo must also work from a clearly labeled recorded case when markets, the model, or Alpaca are unavailable.

## 8. Evaluation gates

- Zero orders outside options/account permissions.
- Zero naked or unbounded-loss options positions.
- Zero hard-policy violations reaching execution.
- Zero duplicate orders across retry/restart tests.
- Zero unknown/stale/injected evidence accepted.
- 100% typed outputs after at most one bounded repair, otherwise abstain.
- Exact Decision Card replay and tamper detection.
- Twelve of twelve evaluation cases end in the expected safe state.
- Five consecutive golden demos pass; one with network disabled.
- Hosted app works logged out on desktop and mobile.

P&L is reported separately as observed competition paper performance. It is not mixed with safety-test success and is never presented as guaranteed live performance.

## 9. Submission package

- Public MIT repository and logged-out setup path.
- Hosted interactive application.
- 16:9 PNG/JPG cover.
- 2–3 minute presentation video, within LabLab's five-minute/300 MB general guidance.
- 6–8 slide PDF.
- One-page PDF covering AI logic, risk gates, and Alpaca infrastructure.
- Complete title, short description, long description, track, and technology tags.
- Fresh competition paper account ID entered in the intended submission field.
- Up to five tagged build-in-public posts if time permits.
- Submission record tied to exact commit and deployment IDs.

## 10. Remaining decisions

1. Confirm the existing paper account is brand-new, dedicated, begins at $100,000, and has the required options level.
2. Approve the revised prediction-market thesis.
3. Select the model provider and deployment targets.
4. Decide whether social engagement is worth the Day-5 time after the main release is green.
