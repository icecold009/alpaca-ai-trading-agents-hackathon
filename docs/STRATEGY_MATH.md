# RiskCourt probability-edge strategy

RiskCourt compares a calibrated jury probability with a payoff-geometry proxy derived from a defined-risk vertical debit spread. The proxy is a deterministic hurdle, not a claim that an option price reveals a literal physical probability.

## Jury probability

For juror `i`, let `p_i` be its outcome probability, `c_i` its historical calibration score, and `s_i` its confidence stake. Every value is bounded to `[0, 1]`. Calibration shrinks forecasts toward an uninformative 50%:

`p_i_cal = 0.5 + c_i × (p_i - 0.5)`

The deterministic jury aggregate is:

`w_i = c_i × s_i`

`P_jury = Σ(w_i × p_i_cal) / Σ(w_i)`

The system abstains when there are no jurors, total weight is zero, a probability is invalid, or required evidence is missing. Juror prose never enters the arithmetic.

## Market hurdle and entry

For a same-expiry vertical debit spread, let `D` be net debit per share, `W` the strike width, and `S` a configured slippage buffer. The option-implied break-even proxy is:

`P_hurdle = (D + S) / W`

Inputs must satisfy `0 < D`, `0 ≤ S`, and `D + S ≤ W`. Probability edge is:

`edge = P_jury - P_hurdle`

Entry requires `edge ≥ 0.08` after the slippage buffer, valid/fresh evidence, supported 7–21 DTE contracts, bounded bid/ask spread, and every later risk gate. Candidate spreads are ordered deterministically by greatest edge, then lowest debit, nearest supported expiry, and OCC symbols. A failed tie-break or missing input produces abstention.

## Fixed risk and exits

For the MVP, the maximum loss of a debit spread is its debit plus estimated fees:

`max_loss_per_contract = D × 100 + fees`

The per-trade budget is `0.5% × account equity`. Quantity is the lesser of one contract and the whole number of contracts affordable within that budget. If one contract exceeds the budget, no order is allowed. An AI model cannot supply, increase, or override quantity, maximum loss, policy limits, or exit thresholds.

The initial deterministic exit policy takes profit when the spread value reaches `1.5 × entry debit`, triggers a protective exit at `0.5 × entry debit`, exits when the probability edge decays to zero, and exits before the final two trading sessions to expiry. The original full debit remains the disclosed maximum loss because an exit order may not fill at its trigger.

## Hand-calculated recorded example

For three jurors `(p, c, s)` of `(0.62, 0.9, 0.8)`, `(0.58, 0.8, 0.7)`, and `(0.54, 0.7, 0.6)`, calibrated probabilities are `0.608`, `0.564`, and `0.528`; weights are `0.72`, `0.56`, and `0.42`. Therefore `P_jury = 0.97536 / 1.70 = 0.573741176470588…`.

For a `$5.00`-wide SPY call debit spread costing `$1.50` with `$0.10` slippage buffer, `P_hurdle = 1.60 / 5.00 = 0.32`. Edge is `0.253741176470588…`, which clears the `0.08` minimum. Maximum loss is `$1.50 × 100 = $150`. A `$100,000` account has a `$500` per-trade budget, but the MVP cap reduces the mathematically affordable three contracts to exactly one. The automated fixture in `backend/tests/test_strategy_math.py` asserts these values without rounding.
