# RiskCourt: technical write-up

## Product and AI logic

RiskCourt is an autonomous, paper-only options agent built around an AI prediction market. Three independent jurors inspect different evidence classes: market structure, catalyst/news, and volatility/options structure. Each juror returns a structured probability forecast, a confidence stake, uncertainty, invalidation conditions, and the IDs of evidence it actually used. Juror prose is untrusted context; it never has order authority.

The provider boundary enforces a schema, timeout, one repair attempt, call cap, cost cap, and model/prompt version trace. A provider failure, malformed response, missing evidence, or prompt-injection attempt ends in abstention or an explicit error. The deterministic orchestrator aggregates only valid forecasts. For juror `i`, calibration shrinks a probability toward 50%: `p_i' = 0.5 + c_i(p_i − 0.5)`. The aggregate weights each calibrated probability by `w_i = c_i × stake_i`: `P_jury = Σ(w_i p_i') / Σw_i`.

## Option-implied hurdle and entry

RiskCourt selects a same-underlying, same-expiry vertical debit spread from a bounded, timestamped Alpaca option chain. The spread is a defined-risk payoff, not a naked option position. If `D` is debit per share, `W` is strike width, and `S` is a configured slippage buffer, the deterministic break-even proxy is `P_hurdle = (D + S) / W`. This is explicitly a payoff-geometry proxy, not a claim that an option quote reveals a literal physical probability. The agent enters only when `P_jury − P_hurdle ≥ 0.08`, after all data-quality and account gates pass.

## Risk court and execution

The fixed policy rejects stale or missing quotes, crossed/illiquid markets, unsupported expiries, invalid symbols, unknown evidence, disagreement, insufficient edge, excessive drawdown, duplicate intents, expired approvals, and a tripped kill switch. Maximum loss is debit × 100 plus estimated fees. The trade budget is 0.5% of account equity and the MVP cap is one contract; an AI output cannot increase quantity or widen a limit. Approval binds the intent, policy version, option/underlying/account evidence fingerprints, and a short expiry. A deterministic client order ID makes retries idempotent.

The Alpaca Trading API adapters read paper account/clock/positions, SPY bars and quotes, and a bounded option chain. An approved vertical maps to an Alpaca `order_class=mleg` day limit request with explicit buy-to-open and sell-to-open legs. Order lifecycle states, cancellation/rejection, fills, and disconnects are normalized for audit. The exit policy takes profit at 1.5× entry debit, protects at 0.5×, exits when edge decays to zero, and closes before the final two trading sessions. The original debit remains the disclosed maximum loss because an exit may not fill at its trigger.

## Evidence, P&L, and limitations

Recorded mode replays twelve credential-free cases, including positive edge, no edge, stale/missing data, disagreement, provider outage, injection, duplicate intent, and drawdown vetoes. The UI labels recorded data, market-closed state, provider failure, Alpaca rejection, and kill-switch state. P&L snapshots store position value, cost basis, realized/unrealized P&L, maximum loss, timestamps, and evidence IDs; they are paper-performance observations, not expected returns.

The current `main` release has verified local backend/frontend tests, a reproducible verifier, browser/accessibility smoke coverage, and a public recorded Render deployment. Fresh dedicated-account confirmation, the final video, and final submission artifacts remain release gates. No live-money execution path is supported, and no performance claim should be inferred from the recorded fixtures.
