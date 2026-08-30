# RiskCourt video run-of-show

Target length: 2 minutes 30 seconds. This is a recording script, not evidence of a hosted or live paper run. Replace the marked proof frame only after the corresponding release gate is verified.

| Time | Screen | Spoken line / purpose |
|---|---|---|
| 0:00–0:15 | Cover, then Decision Card | “Most AI trading demos stop at a confident forecast. RiskCourt makes the forecast argue against the option payoff, then lets deterministic policy decide whether anything may happen.” |
| 0:15–0:40 | Jury panels and evidence IDs | “Three independent jurors cover market structure, catalysts, and volatility/options structure. They return probabilities, confidence stakes, uncertainty, invalidation, and cited evidence—not orders.” |
| 0:40–1:05 | Formula slide / recorded SPY example | “Calibration shrinks each forecast toward 50% and weights it by calibration times stake. For a debit spread, the hurdle is debit plus slippage divided by strike width. Entry needs at least eight percentage points of edge.” |
| 1:05–1:35 | Risk guardrail slide; click one abstain/failure case | “Freshness, liquidity, expiry, account, drawdown, duplicate, approval, and kill-switch gates all fail closed. The MVP is one contract and caps risk at 0.5% of equity. Stale data or disagreement produces abstain.” |
| 1:35–2:00 | Alpaca infrastructure slide | “In paper mode, Alpaca reads supply the account, clock, underlying bars and quotes, and option chain. An approved vertical maps to an `mleg` day limit request with explicit legs and an idempotent client order ID. The lifecycle and P&L snapshot remain auditable.” |
| 2:00–2:18 | Recorded evaluation / rehearsal evidence | “Before the market is open, twelve credential-free cases replay the same boundaries: trade, abstain, veto, error, injection, outage, duplicate, and drawdown. Five golden rehearsals are timestamped.” |
| 2:18–2:30 | Boundary slide | “This is paper research, not investment advice. The official MCP or CLI proof, market-open paper order, hosted verification, and final submission remain explicit gates. No live-money path exists.” |

## Recording checklist

- Use the seven-slide deck and the local recorded UI as the default path.
- Add a verified market-open paper frame only after FD-035–FD-040 are green; never simulate or imply a fill.
- Redact API keys, secrets, account IDs, order IDs, private URLs, and local filesystem paths from the recording.
- Keep the cover, formula, risk guardrail, Alpaca mapping, evaluation, and limitations visible long enough to read.
- Export MP4 under five minutes and 300 MB, add captions, and confirm playback while logged out.
- Store the final video link only in the LabLab form or a private evidence note; do not add it here until it is public and approved.
