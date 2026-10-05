# RiskCourt: technical write-up

## Product and AI logic

RiskCourt is a local, single-user, paper-only options workstation. Its bounded juror roles inspect supported evidence classes such as market structure, catalysts, and volatility/options structure; an unsupported or missing role abstains. Forecasts include a confidence stake, invalidation conditions, and the IDs of evidence actually used. Juror prose is untrusted context; it never has order authority.

The provider boundary enforces a schema, per-call and total time limits, call and cost caps, and model/prompt version trace. A provider failure, malformed response, missing evidence, or prompt-injection attempt ends in abstention or an explicit error. The deterministic orchestrator aggregates only valid forecasts. Forecast shrinkage uses the versioned fixed code-owned prior `configured_shrinkage_prior_v1`, `c_i = 0.80`: `p_i' = 0.5 + c_i(p_i − 0.5)`. This is a configured prior, not measured historical accuracy. Eligible forecasts and their event contracts are persisted; later settlement evidence can be imported and scored by role, model and prompt. Those metrics are descriptive and never change runtime weights. The aggregate weights each shrunk probability by `w_i = c_i × stake_i`: `P_jury = Σ(w_i p_i') / Σw_i`.

Settlement imports preserve the exact UTF-8 CSV bytes and SHA-256 digest in SQLite.
The event threshold and condition come from the saved forecast contract, not the
import file. An import is rejected before the event horizon, for an observation
after the horizon or more than five minutes before it, or when the observation
does not follow every forecast. The report uses a chronological holdout and only
places a training outcome in the training set when it was resolved before the
first holdout forecast was produced. This enforces temporal ordering in the
stored dataset; it does not independently authenticate an operator-supplied
source label or establish trading profitability.

The optional TypeSafe adapter asks three atomic System One questions in one bounded request:
Noul for the outcome probability, Choice for one supplied evidence anchor (including an explicit
no-supported-evidence option), and Score for evidence quality. TypeSafe confidence and evidence
quality contribute only to a bounded confidence stake; calibration remains code-owned. The adapter
receives role-specific evidence partitions, hashes the sanitized state, records model, question-set,
usage, latency, and validation metadata, and fails closed on stale evidence, unknown IDs,
malformed answers, missing credentials, or provider errors. RISKCOURT_AI_MODE=shadow keeps the
deterministic result while recording a comparison; typesafe is active only when explicitly selected.
Earlier repository notes recorded a provider smoke request and a read-only broker preflight. Those
historical checks are not evidence of this branch's current hosted or account state. Current local
tests use injected broker/provider fakes; no broker order was submitted for this completion work.

## Option-implied hurdle and entry

RiskCourt selects a same-underlying, same-expiry vertical debit spread from a bounded, timestamped Alpaca option chain. The spread is a defined-risk payoff, not a naked option position. If `D` is debit per share, `W` is strike width, and `S` is a configured slippage buffer, the deterministic break-even proxy is `P_hurdle = (D + S) / W`. This is explicitly a payoff-geometry proxy, not a claim that an option quote reveals a literal physical probability. The agent enters only when `P_jury − P_hurdle ≥ 0.08`, after all data-quality and account gates pass.

## Risk court and execution

The fixed policy rejects stale or missing quotes, crossed/illiquid markets, unsupported expiries, invalid symbols, unknown evidence, disagreement, insufficient edge, excessive drawdown, duplicate intents, expired approvals, and a tripped kill switch. Maximum loss is debit × 100 plus estimated fees. The trade budget is 0.5% of account equity and the MVP cap is one contract; an AI output cannot increase quantity or widen a limit. Approval binds the intent, policy version, option/underlying/account evidence fingerprints, and a short expiry. A deterministic client order ID makes retries idempotent.

The Alpaca Trading API adapters read paper account/clock/positions, SPY bars and quotes, and a bounded option chain. An approved vertical maps to an Alpaca `order_class=mleg` day limit request with explicit buy-to-open and sell-to-open legs. Order lifecycle states, cancellation/rejection, fills, and disconnects are normalized for audit. The exit policy takes profit at 1.5× entry debit, protects at 0.5×, exits when edge decays to zero, and closes before the final two trading sessions. The original debit remains the disclosed maximum loss because an exit may not fill at its trigger.

## Evidence, P&L, and limitations

Recorded mode replays twelve credential-free cases, including positive edge, no edge, stale/missing data, disagreement, provider outage, injection, duplicate intent, and drawdown vetoes. The UI labels recorded data, market-closed state, provider failure, Alpaca rejection, and kill-switch state. P&L snapshots store position value, cost basis, realized/unrealized P&L, maximum loss, timestamps, and evidence IDs; they are paper-performance observations, not expected returns.

The current `main` release has verified local backend/frontend tests, a reproducible verifier, browser/accessibility smoke coverage, and a public recorded Render deployment. Fresh dedicated-account confirmation, the final video, and final submission artifacts remain release gates. No live-money execution path is supported, and no performance claim should be inferred from the recorded fixtures.
