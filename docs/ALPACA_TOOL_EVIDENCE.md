# Official Alpaca MCP/CLI evidence (private release artifact)

This file is a redaction-safe capture from the official Alpaca CLI. The internal
RiskCourt capability wrapper is not used as Alpaca MCP/CLI proof.

## Capture checklist

- [x] Official Alpaca MCP server or CLI name and version are visible.
- [x] Paper account read succeeds; account ID, timestamps, and balances are redacted.
- [x] Options approval/trading level read succeeds.
- [x] Market clock read succeeds.
- [x] SPY option-chain read succeeds with expiry/strike range visible; identifiers are redacted.
- [x] Order schema or dry-run is shown with `order_class=mleg`, `time_in_force=day`,
  explicit position intents, and no mutation unless separately approved.
- [x] Read tools and order-mutation tools are shown as separate capabilities.
- [x] Transcript contains timestamps and no API keys, secrets, raw account payloads,
  account IDs, order IDs, private URLs, or chain-of-thought.

## Redacted transcript

```text
Captured at (timezone): 2026-09-04T00:22:35+05:30 (Asia/Calcutta)
Official tool/version: Alpaca CLI 0.0.14
Paper account read: PASS — active paper profile; account reference [REDACTED]
Options approval level: PASS — trading level 3; approval level 3
Market clock: PASS — is_open=true; API timestamps [REDACTED]
SPY option chain: PASS — 100 call snapshots; expiry 2026-09-03; strike range 420-757; contract references [REDACTED]
Order schema/dry-run: PASS — order_class=mleg; time_in_force=day; type=market; qty=1; 2 legs; position_intents=buy_to_open,sell_to_open; no submission
Live paper order lifecycle: PASS — one-contract mleg day-limit; client reference [REDACTED]; status new -> canceled; filled_qty 0; positions 0
Read capability inventory: PASS — profile list, account get, clock, option chain, order list, position list, order schema, dry-run
Mutation capability inventory: PAPER ONLY, APPROVED — order submit and cancel used; no live-account mutation
Transcript hash: sha256:29698b3553bd13ff144179d509c348ad4fb7196d598c70b534ef6049dddc4f73
```

Store the raw transcript and screenshots outside the public repository. Only the
redacted summary and a hash belong in the private release-evidence package.
