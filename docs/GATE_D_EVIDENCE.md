# Gate D evidence

Gate D is the recorded-first autonomous-options milestone. The model boundary can produce
forecasts, but it has no order authority; deterministic jury aggregation and policy code decide
whether a candidate is trade, abstain, veto, or error.

Evidence captured on 2026-08-30:

- The FD-045 registry validates 12 unique scenarios and all four expected outcomes.
- The registry records zero order attempts and explicitly rejects unknown evidence.
- The FD-046 judge view shows each juror probability, confidence stake, calibration, evidence
  count, aggregate odds, option-implied hurdle, edge margin, legs, maximum loss, verdict, order,
  and paper P&L.
- FD-047 replay controls demonstrate market-closed, missing-quote, provider-failure,
  Alpaca-rejection, and kill-switch fallbacks with keyboard-safe status announcements.
- FD-048 ran five consecutive fresh-browser recorded rehearsals; timestamps are in
  docs/DEMO_REHEARSAL.md.

The Alpaca paper order remains a later market-hours gate. No order was submitted while the
market was closed and the latest quote was stale.
