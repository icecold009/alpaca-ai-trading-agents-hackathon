# Security and financial-claim review

Baseline review recorded on 2026-08-30 against the pre-polish release. The standard Codex
Security scan reported zero findings across the repository scope. The tracked-file secret scan
also passed; the complete cleanup-branch verifier passed again on 2026-09-04.

Validated controls:

- Settings accepts only the official Alpaca paper endpoint and rejects both live-trading flags.
- Provider and juror outputs are typed with extra fields rejected; cited evidence must be within
  the supplied evidence boundary.
- Order mapping is paper-only, explicit-approval gated, idempotent, and limited to defined-risk
  multi-leg orders.
- Decision-card exports sanitize secret, API-key, and account-id fields.
- The public API exposes recorded-case reads only; the frontend renders text data without raw HTML
  insertion.
- Paper trading and options-risk disclaimers are visible in the recorded UI and documentation;
  no return or live-performance claim is made.

Remaining operational review: confirm hosted CORS/origin policy, response headers, server-side
secret storage, log retention, and account-identifier handling after each deployment. No live or
paper order is submitted by the public recorded surface.

The repository now includes `scripts/verify_hosted.py`, a GET-only check for those release
boundaries that validates `/healthz`, recorded-case reachability, fail-closed flags, and the
exact frontend-origin CORS header without printing response payloads. It has passed against the
public Render frontend and backend; private account and paper-order evidence remains separate.
