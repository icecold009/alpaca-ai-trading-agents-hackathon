# Official Alpaca MCP/CLI evidence (private release artifact)

This file is a redaction-safe capture template. The internal RiskCourt capability
wrapper is not official Alpaca MCP/CLI proof, so this record must be completed
from the official Alpaca tool on the competition account before submission.

## Capture checklist

- [ ] Official Alpaca MCP server or CLI name and version are visible.
- [ ] Paper account read succeeds; account ID, timestamps, and balances are redacted.
- [ ] Options approval/trading level read succeeds.
- [ ] Market clock read succeeds.
- [ ] SPY option-chain read succeeds with expiry/strike range visible; identifiers are redacted.
- [ ] Order schema or dry-run is shown with `order_class=mleg`, `time_in_force=day`,
  explicit position intents, and no mutation unless separately approved.
- [ ] Read tools and order-mutation tools are shown as separate capabilities.
- [ ] Transcript contains timestamps and no API keys, secrets, raw account payloads,
  account IDs, order IDs, private URLs, or chain-of-thought.

## Redacted transcript

```text
Captured at (timezone): [PENDING]
Official tool/version: [PENDING]
Paper account read: PASS — account reference [REDACTED]
Options approval level: [PENDING]
Market clock: [PENDING]
SPY option chain: PASS — contract references [REDACTED]
Order schema/dry-run: [PENDING]
Read capability inventory: [PENDING]
Mutation capability inventory: [PENDING — approval-gated]
Transcript hash: [PENDING]
```

Store the raw transcript and screenshots outside the public repository. Only the
redacted summary and a hash belong in the private release-evidence package.
