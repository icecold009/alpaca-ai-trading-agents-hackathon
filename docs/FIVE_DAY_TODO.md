# RiskCourt — Five-Day Critical TODO

This is the authoritative build checklist after reviewing the live LabLab requirements. It supersedes the earlier equities-only backlog.

**Official cutoff:** September 4, 2026 at 8:30 PM IST

**Constraint:** Finish the release candidate in five focused build days and preserve the remaining time as submission/incident buffer.

**MVP:** An autonomous options agent whose AI jurors form a calibrated probability market and trade only when their aggregated probability exceeds the option-implied break-even hurdle by a safety margin.

## Non-negotiable scope

- Alpaca Trading API plus Alpaca MCP or CLI.
- Options trading on a new, dedicated $100,000 paper account.
- One or two liquid underlyings: start with SPY; add QQQ only if the SPY loop is complete.
- Preferred trade: one-contract, defined-risk vertical debit spread with 7–21 days to expiry; Level-2 long call/put is the documented fallback.
- No 0DTE dependency, naked short options, live-money path, training pipeline, mobile app, authentication system, or multi-broker support.
- Every order has a deterministic maximum-loss cap, idempotent client order ID, exit condition, and audit record.
- Recorded demo and live paper mode must tell the same story and be visibly distinguished.

## Already resolved

- [x] **FD-001 — Verify the official cutoff**
  - Evidence: LabLab event page shows September 4, 2026 at 8:30 PM IST.

- [x] **FD-002 — Confirm eligibility**
  - Evidence: User confirmed eligibility is fine.

- [x] **FD-003 — Confirm team name**
  - Evidence: User confirmed the team name is sorted; do not publish private team details unless requested.

- [x] **FD-004 — Capture all published requirements**
  - Evidence: `docs/EVENT_REQUIREMENTS.md` records challenge, account, submission, judging, social, prize, conduct, and disclosure requirements.

- [x] **FD-005 — Create a paper account and keys**
  - Evidence: User confirmed the account and keys exist. Keys remain outside the repository and chat.

## Immediate user verification — complete before the first judged trade

- [ ] **FD-006 — Verify the final competition account** `User · 10 min`
  - Confirm the created account is brand-new, dedicated to this hackathon, and has never been reused.
  - Confirm starting equity is exactly $100,000.
  - Record only `confirmed/not confirmed` locally; do not add the account ID or keys to the public repository.

- [ ] **FD-007 — Verify options permissions** `User + Backend · 10 min`
  - Check `options_approved_level` and `options_trading_level` through the paper account endpoint.
  - Target Level 3 for multi-leg spreads.
  - If only Level 2 is available by the end of Day 2, activate the long-call/long-put fallback and remove spread claims.

- [ ] **FD-008 — Freeze the revised product thesis** `User · 10 min`
  - Approve: “RiskCourt is an AI prediction market for options alpha: agents stake calibrated probabilities, and deterministic policy trades only when jury odds beat option-implied odds by a safe margin.”
  - Any change after this task must remove equal or greater scope.

## Day 1 — Eligible skeleton and offline story

**Outcome:** A clean repository can replay an eligible options decision from jury forecasts to a recorded trade and P&L card.

- [x] **FD-009 — Start `codex/riskcourt-mvp` from the planning commit** `5 min`
  - Verify: `git branch --show-current` is correct; `main` is untouched.

- [x] **FD-010 — Scaffold backend, frontend, fixtures, scripts, docs, and CI folders** `25 min`
  - Acceptance: No generated dependencies are committed.
  - Verify: repository tree matches the revised architecture.

- [x] **FD-011 — Add MIT license, ignores, editor settings, and secret-safe `.env.example`** `20 min`
  - Acceptance: keys, SQLite data, coverage, Node/Python caches, screenshots, and build output are ignored.
  - Verify: secret scan and `git status --ignored --short`.

- [x] **FD-012 — Configure Python backend tooling** `30 min`
  - Include FastAPI, Pydantic, SQLAlchemy/SQLite, `alpaca-py`, model SDK, pytest, Ruff, and mypy.
  - Verify: import, test, lint, and typecheck commands pass.

- [x] **FD-013 — Configure React frontend tooling** `30 min`
  - Include TypeScript, Vite, Tailwind, Recharts, Vitest, Testing Library, Playwright, and accessibility checks.
  - Verify: build and unit test pass.

- [x] **FD-014 — Enforce recorded/paper-only startup modes** `25 min`
  - Recorded mode needs no secrets; paper mode requires paper credentials; any live endpoint/flag aborts startup.
  - Verify: explicit recorded, paper-missing-key, valid-paper, and live-rejected tests.

- [x] **FD-015 — Define option-domain contracts** `45 min`
  - `EvidenceItem`, `OptionQuote`, `OptionLeg`, `ProbabilityForecast`, `TradeIntent`, `RiskVerdict`, `ApprovalArtifact`, `DecisionEvent`, `ExecutionRecord`, and `PnLSnapshot`.
  - Acceptance: decimal-safe money, timezone-aware timestamps, OCC symbols, expiry, position intent, maximum loss, and evidence IDs are required.
  - Verify: valid/boundary/malformed serialization tests.

- [x] **FD-016 — Specify the probability-edge strategy mathematically** `40 min`
  - Define juror probability, aggregation/calibration, option-implied break-even proxy, minimum edge, spread selection, max loss, profit target, stop, and time exit.
  - Acceptance: one-page formula/example with no model prose deciding order size.
  - Verify: hand-calculated fixture matches code calculations exactly.

- [x] **FD-017 — Create the edge-positive recorded fixture** `35 min`
  - Jurors aggregate to an outcome probability above the option-implied hurdle; risk resizes to one contract; recorded multi-leg order fills and later shows paper P&L.
  - Verify: every ID resolves and the maximum loss is reconstructable.

- [x] **FD-018 — Create the abstain/veto fixture** `30 min`
  - Use stale/missing quotes, disagreement, or insufficient edge.
  - Acceptance: no execution event can follow the veto.

- [x] **FD-019 — Build the recorded-case API and clickable UI shell** `75 min`
  - Show juror odds, market-implied odds, edge, selected option legs, max loss, verdict, order, and P&L.
  - Verify: network-disabled Playwright run completes both fixtures.

- [x] **FD-020 — Commit Gate A** `10 min`
  - Commit: `feat(demo): establish eligible options golden path`.
  - Gate: an offline judge can understand why the options trade occurred or was rejected.

## Day 2 — Probability engine and deterministic capital controls

**Outcome:** The strategy can calculate edge and reject unsafe or low-quality options trades without model authority.

- [x] **FD-021 — Implement probability aggregation and calibration** `45 min`
  - Bound probabilities, weight jurors by declared calibration score, handle disagreement, and produce a deterministic aggregate.
  - Verify: consensus, disagreement, outlier, missing juror, and invalid probability tests.

- [x] **FD-022 — Implement option-implied hurdle calculation** `45 min`
  - Use current debit/width and contract payoff geometry as a documented proxy; do not label it a literal physical probability.
  - Verify: hand-worked vertical-spread examples and zero/invalid quote guards.

- [x] **FD-023 — Implement edge and abstention rules** `30 min`
  - Require a configured minimum probability margin after spread/slippage buffer.
  - Verify: below, equal, and above-threshold cases.

- [x] **FD-024 — Implement contract liquidity filters** `35 min`
  - Require nonzero bid/ask, bounded spread width, supported expiry, valid contract status, and available quote timestamps.
  - Verify: illiquid, crossed, stale, missing-Greek, 0DTE, and unsupported-contract cases.

- [x] **FD-025 — Implement defined-risk sizing** `40 min`
  - Compute exact maximum debit/loss and cap each trade at 0.5% of account equity, one contract for the MVP.
  - Verify: decimal boundary tests and no notional/fractional option quantities.

- [x] **FD-026 — Implement portfolio and daily-loss limits** `35 min`
  - Cap open options risk, positions, pending orders, and daily drawdown; add a global kill switch.
  - Verify: race test toggles kill switch after approval and before execution.

- [x] **FD-027 — Implement freshness, evidence, expiry, and duplicate rules** `35 min`
  - Approval binds option quotes, underlying snapshot, account snapshot, policy version, and short expiry.
  - Verify: mutation matrix and retry/idempotency tests.

- [x] **FD-028 — Implement append-only decision events and replay** `55 min`
  - Hash-chain events, project current state, export sanitized Decision Cards, and detect changes/deletions/reordering.
  - Verify: persist/export/replay round-trip plus tamper tests.

- [x] **FD-029 — Implement deterministic exit policy** `35 min`
  - Encode profit target, maximum loss, edge-decay exit, and time exit; no LLM may widen risk.
  - Verify: entry, hold, profit, loss, stale, expiry-risk, and kill-switch exit cases.

- [x] **FD-030 — Commit Gate B** `10 min`
  - Commit: `feat(strategy): enforce probability edge and options risk policy`.
  - Gate: adversarial inputs cannot produce an order outside the fixed risk envelope.

## Day 3 — Live Alpaca options loop

**Outcome:** One tiny eligible paper options trade is placed, monitored, and tied to a Decision Card on the fresh account.

- [x] **FD-031 — Build paper account/clock/positions adapter** `35 min`
  - Capture equity, options buying power, options levels, positions, pending orders, and market clock.
  - Verify: recorded contract tests and one sanitized live paper read.

- [x] **FD-032 — Build underlying market-data adapter** `30 min`
  - Fetch recent SPY bars/quotes and record feed/timestamp provenance.
  - Verify: missing/rate-limit/stale/live cases.

- [x] **FD-033 — Build option-chain adapter** `50 min`
  - Query calls/puts by expiry and strike range; capture indicative/OPRA feed, quotes, IV, Greeks when available, and missing-value reasons.
  - Verify: pagination, missing Greeks, stale quote, empty chain, and one live chain.

- [x] **FD-034 — Build candidate-spread selector** `45 min`
  - Generate only same-underlying, same-expiry, supported-width, liquid vertical debit spreads.
  - Verify: candidate ordering is deterministic and every candidate has reconstructable max loss/break-even.

- [ ] **FD-035 — Connect Alpaca MCP or CLI requirement** `35 min`
  - Preferred: MCP for read-only account/market research and CLI for doctor/schema/dry-run evidence.
  - Acceptance: execution permission stays outside AI research tools.
  - Verify: sanitized transcript and enabled-tool inventory.

- [ ] **FD-036 — Implement multi-leg paper order submission** `60 min`
  - Use `order_class=mleg`, one contract, day time-in-force, explicit position intents, limit price, and deterministic client order ID.
  - Fallback: Level-2 single long option with the same risk controls.
  - Verify: mocked request mapping, reject paths, duplicate retry, and one tiny live paper order.

- [ ] **FD-037 — Implement order updates, cancellation, and position monitoring** `50 min`
  - Persist submitted, accepted, partial/filled, canceled, rejected, replacement, and disconnect states.
  - Verify: recorded lifecycle tests and live terminal-state smoke.

- [ ] **FD-038 — Implement P&L snapshots and exit execution** `45 min`
  - Record realized/unrealized paper P&L, strategy cost, max risk, and timestamps; execute deterministic exits.
  - Verify: recorded profit/loss scenarios and live read after the paper order.

- [x] **FD-039 — Preserve competition-account integrity** `20 min`
  - Never reset/delete/reuse the final account after judged activity begins. Keep the account ID and keys out of public source.
  - Verify: submission checklist contains the account-ID field without committing the value.

- [ ] **FD-040 — Commit Gate C** `10 min`
  - Commit: `feat(alpaca): complete auditable options paper loop`.
  - Gate: RiskCourt and the Alpaca dashboard show the same eligible options order and status.

## Day 4 — Autonomous AI jury, evaluation, and judge UI

**Outcome:** The agent autonomously forms forecasts, trades only valid edge, and visibly proves originality and safety.

- [x] **FD-041 — Define the model provider boundary** `25 min`
  - Structured outputs, timeout, one repair attempt, call/cost cap, deterministic test stub, and prompt/model version capture.
  - Verify: provider contract tests.

- [x] **FD-042 — Implement three independent jurors** `60 min`
  - Juror A: price/market structure; Juror B: news/catalyst; Juror C: volatility/options structure.
  - Each returns probability, confidence stake, cited evidence, uncertainty, and invalidation—not an order.
  - Verify: valid, abstain, hallucinated ID, and injection cases per juror.

- [ ] **FD-043 — Implement jury orchestration** `45 min`
  - Run independent forecasts, deterministic aggregation, option-hurdle comparison, risk verdict, approval, execution, and monitoring.
  - Acceptance: any partial failure or insufficient edge ends in abstention.
  - Verify: success, disagreement, provider failure, malformed output, timeout, and veto tests.

- [ ] **FD-044 — Add prompt-injection and evidence-boundary tests** `40 min`
  - Treat news/tool text as untrusted data and block instructions from changing tools, symbols, policy, or output schema.
  - Verify: ten adversarial cases and zero execution attempts.

- [ ] **FD-045 — Build a 12-case evaluation set** `60 min`
  - Balance trade/abstain/veto/error; include stale quotes, illiquidity, no edge, disagreement, injection, duplicate, drawdown, and provider outage.
  - Verify: expected outcome for all 12; zero unauthorized orders and zero unknown evidence accepted.

- [ ] **FD-046 — Build the jury-vs-market UI** `75 min`
  - Show juror probabilities/stakes, aggregate odds, option-implied hurdle, edge margin, chosen legs, max loss, verdict, order, and current P&L.
  - Verify: an unfamiliar viewer explains the edge without narration.

- [ ] **FD-047 — Complete replay, failure, accessibility, and responsive states** `60 min`
  - Recorded/live badges, market closed, missing quote, no edge, provider failure, Alpaca rejection, kill switch, keyboard, contrast, and reduced motion.
  - Verify: Axe plus manual keyboard/mobile pass and network-disabled E2E.

- [ ] **FD-048 — Run five consecutive golden demos** `35 min`
  - One live/read-only or paper path, one recorded trade, one abstention, one failure fallback; core story under two minutes.
  - Verify: timestamped rehearsal record.

- [ ] **FD-049 — Commit Gate D** `10 min`
  - Commit: `feat(agent): deliver autonomous options prediction market`.
  - Gate: all 12 cases are safe and the differentiated mechanism is obvious within 15 seconds.

## Day 5 — Release, evidence, and submission

**Outcome:** Hosted, reproducible, consistent submission is completed before the official cutoff.

- [ ] **FD-050 — Add full verification command and CI** `35 min`
  - Run backend tests/lint/types, frontend tests/build, fixture validation, 12-case evaluation, secret scan, and recorded E2E.
  - Verify: clean checkout produces one green report.

- [ ] **FD-051 — Run security and financial-claim review** `40 min`
  - Review secrets, CORS, unsafe HTML, tool authority, injection, logs, exports, dependency issues, account identifiers, paper/live wording, and options-risk disclosure.
  - Acceptance: no unresolved high finding and no unsupported return claim.

- [ ] **FD-052 — Deploy backend and frontend** `75 min`
  - Use an accepted platform, server-side secrets, persistent storage, redacted logs, health endpoint, and recorded fallback.
  - Verify: incognito desktop/mobile hosted golden path and restart test.

- [ ] **FD-053 — Create the one-page technical write-up** `45 min`
  - Cover AI logic, probability aggregation, option-implied hurdle, risk gates, Alpaca Trading API/MCP/CLI path, execution, exit, P&L, and limitations.
  - Verify: exactly one page when exported to PDF and consistent with code.

- [ ] **FD-054 — Finish public README** `40 min`
  - GIF/image, pitch, demo, paper-only disclosure, architecture, strategy formula, Alpaca mapping, recorded-first setup, evaluation, P&L snapshot, limitations, license.
  - Verify: clean-clone setup and logged-out links.

- [ ] **FD-055 — Produce cover, screenshots, and PDF slides** `75 min`
  - Show jury odds vs market odds, selected spread, deterministic max loss, execution, and P&L.
  - Verify: 16:9 PNG/JPG cover; readable at thumbnail size; 6–8-slide PDF.

- [ ] **FD-056 — Record the 2–3 minute video** `75 min`
  - Hook in 15 seconds, live behavior, Alpaca proof, formula, safety, paper P&L, business/originality, and limitations.
  - Verify: MP4/link accepted by form, under five minutes and 300 MB, captions, no secrets.

- [ ] **FD-057 — Draft all LabLab fields** `40 min`
  - Title ≤50 chars, summary ≤255 chars, long description ≥100 words, track, technologies, cover, video, slides, public repo, platform, app URL, account ID, and up to five social links.
  - Verify: field-by-field comparison with the live form.

- [ ] **FD-058 — Publish up to five build-in-public posts** `P1 · User · 60 min`
  - Only if the release candidate is safe. Tag LabLab and Alpaca and submit exact links.
  - Never share keys, sensitive account details, or unqualified performance claims.

- [ ] **FD-059 — Freeze the release candidate** `25 min`
  - Full verification, clean tree, exact commit SHA, deployment IDs, consistent metrics, and no post-freeze feature work.
  - Verify: release evidence file plus logged-out checks.

- [ ] **FD-060 — Submit and independently verify** `30 min`
  - Submit before September 4 at 8:30 PM IST with several hours of buffer.
  - Reopen in incognito; confirm every link/media/field and preserve submission time, URL, commit, deployment, and account linkage privately.

## Cut order if behind

Cut in this order without weakening eligibility or the core story:

1. Social posts beyond the first useful post.
2. QQQ support; keep SPY only.
3. PDF Decision Card; keep JSON/web replay.
4. Advanced charts and animations.
5. Live AI during the public demo; keep evaluated recorded AI output plus a private/live proof.
6. Multi-leg spreads only if Level 3 is unavailable; use the Level-2 long-option fallback.

Never cut:

- Options incorporation.
- Trading API plus MCP or CLI proof.
- Autonomous agent behavior.
- Fresh $100,000 paper account and account ID submission.
- Deterministic risk/exit policy.
- Public repository, hosted app, cover, video, slides, one-page write-up, and required LabLab fields.
