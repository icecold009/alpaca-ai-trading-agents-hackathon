# RiskCourt — Detailed Execution TODO

This is the execution contract for the [prize-winning plan](./PRIZE_WINNING_PLAN.md). It decomposes the MVP into small, ordered tasks with dependencies, acceptance criteria, and verification. Check an item only after its verification passes.

## Build operating rules

- **Plan ownership:** Handed off; sequencing and verification are fully specified here.
- **Implementation mode:** Autonomous once implementation is authorized.
- **Review pauses:** Stop only at Gates 1–8 or when an external credential/organizer decision blocks the critical path.
- **Git:** Start implementation from this planning checkpoint on a new `codex/riskcourt-mvp` feature branch. Commit at every gate. Do not commit or merge directly to `main`.
- **Commit format:** `type(scope): outcome`, for example `feat(risk): enforce portfolio exposure cap`.
- **Priority:** P0 is required for submission. P1 may begin only after all P0 gates through Gate 6 are green. P2 belongs after the hackathon.
- **Verification:** Prefer deterministic automated checks. Every live Alpaca check must have a recorded-fixture equivalent.
- **Demo truth:** Clearly label recorded data, simulated fills, and live paper activity. Never imply that paper performance is live performance.
- **Secrets:** Alpaca/model credentials stay in local or hosted secret stores. Never paste them into chat, source, fixtures, logs, screenshots, issues, or submission copy.
- **Scope freeze:** US equities only, 5–10 allowlisted symbols, paper trading only, three AI roles, one deterministic risk kernel, one judge-facing workflow.
- **Capacity:** The 80 estimated P0 micro-tasks total approximately 43.8 hands-on hours. Reserve at least 6 additional hours for dependency delays, organizer changes, and submission buffer; cut P1 work first and P0 presentation extras second if the schedule slips.

## Priority definitions

- **P0:** Required to tell and prove the complete RiskCourt story.
- **P1:** Improves judge impact but is safe to cut.
- **P2:** Post-hackathon expansion; do not build during the competition.

## Critical path

`Organizer/account setup → repository skeleton → typed contracts → fixture demo → risk kernel → audit/replay → Alpaca reads → safe execution → AI roles → judge UI → evaluation → deploy → submission`

## Daily allocation

| Date | Primary outcome | Planned tasks |
|---|---|---|
| Aug 29 | Decisions, scaffolding, offline clickable story | RC-001–RC-016 |
| Aug 30 | Deterministic risk and replay foundation | RC-017–RC-030 |
| Aug 31 | Alpaca paper integration during market hours | RC-031–RC-043 |
| Sep 1 | Bounded multi-agent decision loop | RC-044–RC-054 |
| Sep 2 | Judge-facing UI and reproducible evaluation | RC-055–RC-065 |
| Sep 3 | Hosted verification and submission assets | RC-066–RC-076 |
| Sep 4 | Freeze, submit early, verify submission | RC-077–RC-080 |

## Phase 0 — External decisions and event lock

- [ ] **RC-001 — Record the authoritative deadline** `P0 · User · 10 min`
  - Depends on: none.
  - Do: Open the enrolled LabLab dashboard and Discord announcements. Record the cutoff timestamp, timezone, and source link in `docs/EVENT_NOTES.md`.
  - Acceptance: One unambiguous ISO-8601 deadline and a human-readable local-time conversion are recorded.
  - Verify: A second person or independent timezone converter confirms the conversion.

- [ ] **RC-002 — Confirm registration and team eligibility** `P0 · User · 10 min`
  - Depends on: RC-001.
  - Do: Confirm LabLab enrollment, Discord membership, team name, team members, and that the team size is within the published 1–6 range.
  - Acceptance: `docs/EVENT_NOTES.md` lists enrollment status and final team roster without private identifiers.
  - Verify: Team dashboard shows every intended member.

- [ ] **RC-003 — Resolve organizer ambiguities** `P0 · User · 20 min`
  - Depends on: RC-002.
  - Do: Confirm prize pool, whether Trading API + MCP + CLI are all mandatory, and any sponsor branding or demo requirements.
  - Acceptance: Each open question is marked `confirmed`, `not required`, or `awaiting organizer`; source links/screenshots are retained outside the public repository if private.
  - Verify: Compare answers against the event dashboard immediately before submission.

- [ ] **RC-004 — Approve the product thesis and name** `P0 · User · 15 min`
  - Depends on: none.
  - Do: Approve `RiskCourt — The AI trading desk that argues before it acts`, or replace it now.
  - Acceptance: Name, tagline, one-sentence pitch, and target customer are frozen in `docs/PRODUCT_BRIEF.md`.
  - Verify: An unfamiliar person can repeat the problem and differentiated behavior after reading only those four lines.

- [ ] **RC-005 — Assign owners and availability** `P0 · User · 15 min`
  - Depends on: RC-002.
  - Do: Assign one accountable owner for backend, frontend/design, evaluation, deployment, video/slides, and final submission. Record daily availability.
  - Acceptance: Every P0 workstream has exactly one accountable owner, even if the same person owns several.
  - Verify: No task relies on an unnamed “team” owner.

- [ ] **RC-006 — Select model provider and budget cap** `P0 · User + Backend · 20 min`
  - Depends on: RC-004.
  - Do: Select one structured-output-capable model, define the environment variable name, maximum per-case calls, timeout, retry count, and total budget.
  - Acceptance: `docs/PRODUCT_BRIEF.md` records the selected model/configuration without credentials.
  - Verify: Provider account is active and one minimal structured-output call succeeds locally.

- [ ] **RC-007 — Prepare an Alpaca paper account** `P0 · User · 20 min`
  - Depends on: none.
  - Do: Create or select a paper-only account and generate paper credentials. Do not create a live-trading path.
  - Acceptance: Paper account ID is available locally; keys exist only in a secret store or ignored `.env`.
  - Verify: Retrieve account status and buying power from the paper endpoint without printing secrets.

- [ ] **RC-008 — Choose deployment targets** `P0 · DevOps · 20 min`
  - Depends on: RC-005.
  - Do: Pick one static frontend host and one Python/WebSocket-capable backend host based on accounts already available.
  - Acceptance: `docs/DEPLOYMENT.md` records provider, region, free-tier limits, secret mechanism, sleep/cold-start behavior, and fallback.
  - Verify: Empty health-check deployments are possible on both targets by Aug 30.

### Gate 1 — Scope lock

- [ ] Deadline, team, product name, model, Alpaca paper account, and deployment choices are recorded.
- [ ] All unresolved organizer questions have an owner and a latest-decision time.
- [ ] Commit checkpoint: `docs(plan): lock event and product decisions`.

## Phase 1 — Repository foundation

- [ ] **RC-009 — Create the implementation branch** `P0 · Git · 5 min`
  - Depends on: Gate 1.
  - Do: Create `codex/riskcourt-mvp` from the latest planning commit.
  - Acceptance: All implementation changes occur on that branch; `main` remains untouched.
  - Verify: `git branch --show-current` returns `codex/riskcourt-mvp` and `git status --short --branch` is clean.

- [ ] **RC-010 — Establish the repository layout** `P0 · Full stack · 20 min`
  - Depends on: RC-009.
  - Do: Create `backend/`, `frontend/`, `fixtures/`, `scripts/`, `docs/`, and `.github/workflows/` with short purpose READMEs where useful.
  - Acceptance: The structure matches the architecture and contains no generated dependencies.
  - Verify: `git status --short` lists only intended source/configuration files.

- [ ] **RC-011 — Add repository hygiene files** `P0 · Git · 15 min`
  - Depends on: RC-010.
  - Do: Add `.gitignore`, `.editorconfig`, `.gitattributes`, MIT `LICENSE`, and `.env.example` with placeholder names only.
  - Acceptance: Python caches, Node modules, build output, SQLite runtime files, coverage, Playwright artifacts, and all `.env*` secrets are ignored while `.env.example` remains tracked.
  - Verify: Create temporary ignored examples, run `git status --ignored --short`, then remove them without committing.

- [ ] **RC-012 — Scaffold the Python backend** `P0 · Backend · 30 min`
  - Depends on: RC-010.
  - Do: Configure Python 3.12, FastAPI, Pydantic settings, SQLAlchemy, Alembic, pytest, Ruff, mypy, HTTP client, `alpaca-py`, and the selected model SDK.
  - Acceptance: A minimal app imports and the dependency lock file is committed.
  - Verify: `python -m pytest backend/tests` and the configured lint/type commands pass.

- [ ] **RC-013 — Scaffold the React frontend** `P0 · Frontend · 30 min`
  - Depends on: RC-010.
  - Do: Configure React, TypeScript, Vite, Tailwind, Recharts, Vitest, Testing Library, Playwright, ESLint, and formatting.
  - Acceptance: The app renders a RiskCourt shell with no console errors and dependencies are locked.
  - Verify: `npm --prefix frontend run build` and `npm --prefix frontend run test -- --run` pass.

- [ ] **RC-014 — Define local developer commands** `P0 · Full stack · 20 min`
  - Depends on: RC-012, RC-013.
  - Do: Add documented commands for backend dev, frontend dev, tests, lint, typecheck, browser tests, fixture generation, and full verification.
  - Acceptance: A clean clone can follow `README.md` without guessing directories or environment variable names.
  - Verify: Execute every documented no-secret command exactly as written on Windows PowerShell.

- [ ] **RC-015 — Add configuration and startup guards** `P0 · Backend · 30 min`
  - Depends on: RC-012.
  - Do: Create typed settings for `recorded` and `paper` modes. Hard-code rejection of live Alpaca base URLs and live-trading flags.
  - Acceptance: Recorded mode boots without credentials; paper mode requires paper credentials; live configuration exits with a clear error.
  - Verify: Unit tests cover all three startup paths and assert that no live execution client can be constructed.

- [ ] **RC-016 — Add baseline CI and secret scanning** `P0 · DevOps · 30 min`
  - Depends on: RC-011–RC-015.
  - Do: Add CI for backend tests/lint/types, frontend test/build, and a maintained secret scanner.
  - Acceptance: CI runs on branch pushes and pull requests; failures block the verification job.
  - Verify: Push a safe checkpoint when authorized and confirm one green run; locally validate the workflow syntax first.

### Gate 2 — Reproducible skeleton

- [ ] Recorded-mode backend and frontend boot from documented commands.
- [ ] Paper/live startup guards are tested.
- [ ] Backend and frontend test/build checks pass locally.
- [ ] Commit checkpoint: `chore(repo): establish verified application skeleton`.

## Phase 2 — Contracts and fixture-first golden path

- [ ] **RC-017 — Define `EvidenceItem`** `P0 · Backend · 20 min`
  - Depends on: RC-012.
  - Do: Implement fields for ID, type, source, symbol, observation timestamp, payload hash, summary, and raw reference.
  - Acceptance: IDs/hashes are deterministic; timezone-naive timestamps and missing provenance are rejected.
  - Verify: Pydantic validation and serialization round-trip tests pass.

- [ ] **RC-018 — Define `TradeIntent`** `P0 · Backend · 25 min`
  - Depends on: RC-017.
  - Do: Implement symbol, side, notional, order type, time in force, confidence, thesis, evidence IDs, invalidation conditions, expiry, and model/prompt version.
  - Acceptance: Free-form quantities, unsupported order types, empty evidence, expired timestamps, and out-of-range confidence fail validation.
  - Verify: Valid, boundary, malformed, and adversarial schema tests pass.

- [ ] **RC-019 — Define risk, audit, and execution contracts** `P0 · Backend · 30 min`
  - Depends on: RC-018.
  - Do: Implement `PortfolioSnapshot`, `RiskVerdict`, `DecisionEvent`, `ApprovalArtifact`, and `ExecutionRecord`.
  - Acceptance: Every downstream state references a case/intent; money uses decimal-safe types; enums are exhaustive.
  - Verify: Round-trip tests and mypy exhaustiveness checks pass.

- [ ] **RC-020 — Publish frontend-safe schemas** `P0 · Full stack · 25 min`
  - Depends on: RC-017–RC-019.
  - Do: Generate or hand-maintain TypeScript types from the backend OpenAPI contract with a drift-check command.
  - Acceptance: Frontend does not duplicate incompatible domain definitions.
  - Verify: Regeneration produces no uncommitted diff and frontend typecheck passes.

- [ ] **RC-021 — Create the approved-after-resize fixture** `P0 · Product + Backend · 30 min`
  - Depends on: RC-019.
  - Do: Build a deterministic case in which the Thesis Agent proposes 8% notional and the Risk Kernel resizes it to 2% with cited evidence.
  - Acceptance: Fixture includes account snapshot, evidence, all role outputs, verdict, order lifecycle, and final Decision Card.
  - Verify: JSON schema validation passes and every referenced ID resolves.

- [ ] **RC-022 — Create the stale-evidence veto fixture** `P0 · Product + Backend · 25 min`
  - Depends on: RC-019.
  - Do: Build a deterministic case with expired market evidence that must fail closed.
  - Acceptance: No execution event exists after the veto and the UI-facing reason is specific.
  - Verify: Fixture validation plus a negative assertion that no order record is produced.

- [ ] **RC-023 — Implement recorded-case API routes** `P0 · Backend · 30 min`
  - Depends on: RC-021, RC-022.
  - Do: Add routes to list cases, load a case, step/replay events, reset replay, and export a Decision Card.
  - Acceptance: Routes work without Alpaca or model credentials and expose a `recorded: true` provenance flag.
  - Verify: FastAPI integration tests cover happy, missing, corrupt, and reset paths.

- [ ] **RC-024 — Build a fixture-driven UI skeleton** `P0 · Frontend · 45 min`
  - Depends on: RC-020, RC-023.
  - Do: Render case header, evidence, three role panels, risk verdict, order status, and recorded-data badge using the two fixtures.
  - Acceptance: Both cases are understandable in a 1440×900 viewport without opening developer tools.
  - Verify: Component tests plus screenshots for approve/resize and veto states.

### Gate 3 — Offline demo safety net

- [ ] Both golden cases run with network access disabled.
- [ ] Recorded provenance is obvious on every relevant screen.
- [ ] A Playwright smoke test reaches the final Decision Card for both cases.
- [ ] Commit checkpoint: `feat(demo): deliver fixture-first golden path`.

## Phase 3 — Deterministic risk and replay engine

- [ ] **RC-025 — Implement symbol allowlist and market-status rules** `P0 · Backend · 25 min`
  - Depends on: RC-019.
  - Do: Reject symbols outside configuration and reject uncertain/closed-market execution unless the order policy explicitly permits queued paper orders.
  - Acceptance: Symbol normalization cannot bypass the allowlist.
  - Verify: Parameterized tests cover casing, whitespace, unsupported symbols, and unknown market state.

- [ ] **RC-026 — Implement evidence completeness and staleness rules** `P0 · Backend · 30 min`
  - Depends on: RC-017, RC-018.
  - Do: Require two distinct evidence items, matching symbols, recent observation timestamps, resolved IDs, and at least one invalidation condition.
  - Acceptance: Hallucinated, duplicate, cross-symbol, future-dated, and stale evidence vetoes the intent.
  - Verify: Parameterized tests cover every rejection reason and exact reason code.

- [ ] **RC-027 — Implement position-size resizing** `P0 · Backend · 30 min`
  - Depends on: RC-019.
  - Do: Cap new position notional at 2% of equity using decimal arithmetic and current exposure.
  - Acceptance: Oversized but otherwise valid trades return `resize`; zero/negative/rounding-invalid sizes return `veto`.
  - Verify: Boundary tests at below, equal to, and above the cap pass without floating-point drift.

- [ ] **RC-028 — Implement portfolio exposure and position-count rules** `P0 · Backend · 30 min`
  - Depends on: RC-019.
  - Do: Enforce 20% gross exposure, three open positions, and one pending order per symbol.
  - Acceptance: Resized orders cannot cause the post-trade portfolio to exceed any cap.
  - Verify: Scenario matrix covers empty, near-limit, at-limit, pending-order, and short-position cases.

- [ ] **RC-029 — Implement loss limit and kill switch** `P0 · Backend · 30 min`
  - Depends on: RC-019.
  - Do: Enforce the 1% daily loss threshold and global/manual kill switch before every execution.
  - Acceptance: Kill state cannot be overridden by model output or a stale approval artifact.
  - Verify: Concurrency test toggles the kill switch between approval and execution and confirms no order is sent.

- [ ] **RC-030 — Implement intent deduplication and expiry** `P0 · Backend · 30 min`
  - Depends on: RC-018.
  - Do: Compute canonical intent hashes, detect duplicates, expire intents/approvals, and specify idempotent replay behavior.
  - Acceptance: Retrying the same intent never creates a second execution record.
  - Verify: Unit and integration tests cover reordered JSON keys, process retry, and expired approval.

- [ ] **RC-031 — Implement verdict composition** `P0 · Backend · 25 min`
  - Depends on: RC-025–RC-030.
  - Do: Run rules in deterministic order and return outcome, approved notional, triggered rules, machine codes, and readable reasons.
  - Acceptance: A veto dominates resize/approve; the same inputs always produce byte-equivalent normalized output.
  - Verify: Snapshot tests cover representative approve, resize, and multi-rule veto cases.

- [ ] **RC-032 — Implement append-only event persistence** `P0 · Backend · 40 min`
  - Depends on: RC-019.
  - Do: Add database models/migration and service for monotonically sequenced immutable Decision Events.
  - Acceptance: Updates/deletes are unavailable through application code; duplicate sequence numbers are rejected.
  - Verify: Migration test, append/concurrency test, and repository API test pass on a fresh SQLite database.

- [ ] **RC-033 — Implement case projection and replay** `P0 · Backend · 35 min`
  - Depends on: RC-032.
  - Do: Derive current case state from events, replay from sequence zero, and export normalized JSON.
  - Acceptance: Rebuilding a case after process restart yields the same state and verdict.
  - Verify: Fixture → persist → export → replay round-trip is exactly equivalent after removing generated timestamps.

- [ ] **RC-034 — Add tamper evidence** `P0 · Backend · 25 min`
  - Depends on: RC-032.
  - Do: Chain event hashes or otherwise detect event payload/order modification.
  - Acceptance: Changing, inserting, deleting, or reordering a persisted event fails verification.
  - Verify: Four explicit tamper tests pass.

### Gate 4 — Capital safety core

- [ ] All hard limits have allow/boundary/reject tests.
- [ ] A model string cannot override any deterministic rule.
- [ ] Replay is deterministic and tampering is detected.
- [ ] Commit checkpoint: `feat(risk): enforce deterministic policy and audit replay`.

## Phase 4 — Alpaca read and execution integration

- [ ] **RC-035 — Implement Alpaca account and clock adapter** `P0 · Backend · 30 min`
  - Depends on: RC-007, RC-015.
  - Do: Fetch paper account status, equity, buying power, positions, pending orders, and market clock through a typed adapter.
  - Acceptance: External payloads are translated into internal snapshots and never leak credentials.
  - Verify: Recorded contract tests plus one live paper smoke with sanitized logs.

- [ ] **RC-036 — Implement market bars/quotes adapter** `P0 · Backend · 35 min`
  - Depends on: RC-007, RC-017.
  - Do: Fetch recent IEX bars/quotes for allowlisted symbols and convert them to Evidence Items.
  - Acceptance: Feed, timestamp, symbol, and source appear in evidence; rate-limit and missing-data errors are typed.
  - Verify: Recorded responses plus one live check for two allowlisted symbols.

- [ ] **RC-037 — Implement news/movers adapter** `P0 · Backend · 35 min`
  - Depends on: RC-007, RC-017.
  - Do: Fetch latest relevant news and market movers with bounded result counts and HTML-safe summaries.
  - Acceptance: Untrusted HTML is not rendered; duplicate headlines are deduplicated; source URLs remain traceable.
  - Verify: Contract tests include empty, duplicate, malformed, and rate-limited responses.

- [ ] **RC-038 — Connect the official Alpaca MCP read path** `P0 · Backend · 45 min`
  - Depends on: RC-007, RC-017.
  - Do: Configure read-only account/stock/news toolsets and wrap MCP calls behind the same internal evidence interfaces.
  - Acceptance: Research roles can use MCP reads but receive no execution tool capability.
  - Verify: Enumerate enabled toolsets without secrets and execute one read-only paper-account or market-data call.

- [ ] **RC-039 — Add evidence snapshot assembly** `P0 · Backend · 35 min`
  - Depends on: RC-035–RC-038.
  - Do: Assemble an atomic snapshot with account, portfolio, clock, market, and news evidence plus freshness metadata.
  - Acceptance: Partial or inconsistent snapshots are marked unusable and cannot reach AI/execution.
  - Verify: Tests simulate one failed source, clock skew, late response, and mismatched symbol.

- [ ] **RC-040 — Implement approval artifacts** `P0 · Backend · 30 min`
  - Depends on: RC-031, RC-039.
  - Do: Bind an approval to the normalized intent, verdict, portfolio snapshot hash, policy version, and short expiry.
  - Acceptance: Any changed field or expired artifact fails verification immediately before execution.
  - Verify: Mutation matrix tests every bound field.

- [ ] **RC-041 — Implement paper order submission** `P0 · Backend · 45 min`
  - Depends on: RC-035, RC-040.
  - Do: Map approved intents to supported Alpaca order requests with deterministic client order IDs.
  - Acceptance: The adapter is constructed only in paper mode; unsupported types fail before network activity.
  - Verify: Mock tests for request mapping and one tiny policy-compliant paper order during market hours.

- [ ] **RC-042 — Implement order updates and cancellation** `P0 · Backend · 40 min`
  - Depends on: RC-041.
  - Do: Consume paper trade updates, persist state transitions, reconnect safely, and allow policy-triggered cancellation.
  - Acceptance: Submitted, accepted, partial-fill, fill, cancel, reject, and disconnect paths all produce ordered events.
  - Verify: Recorded stream tests plus one live submitted-to-terminal-state smoke.

- [ ] **RC-043 — Add Alpaca CLI verification script** `P0 · DevOps · 30 min`
  - Depends on: RC-007, RC-041.
  - Do: Document/run `alpaca doctor`, account inspection, order schema, `--dry-run`, and client-order-ID lookup with sanitized capture.
  - Acceptance: CLI proves the same paper account/order context without exposing credentials.
  - Verify: `docs/evidence/alpaca-cli-sanitized.txt` contains command names, timestamps, and safe results only.

### Gate 5 — Verified Alpaca loop

- [ ] One tiny paper order is visible in RiskCourt and the Alpaca dashboard.
- [ ] Duplicate submission returns the existing execution record.
- [ ] MCP is demonstrably read-only; CLI and Trading API evidence is sanitized.
- [ ] Commit checkpoint: `feat(alpaca): complete safe paper-trading integration`.

## Phase 5 — Bounded AI committee

- [ ] **RC-044 — Define the model-provider interface** `P0 · Backend · 25 min`
  - Depends on: RC-006, RC-018.
  - Do: Create a provider-neutral structured-generation interface with timeout, token/cost capture, and deterministic test stub.
  - Acceptance: Domain services do not import provider-specific response types.
  - Verify: Stub and real-provider smoke both satisfy the same contract tests.

- [ ] **RC-045 — Implement Scout prompt and validator** `P0 · AI · 35 min`
  - Depends on: RC-039, RC-044.
  - Do: Select one opportunity from the allowlist using only supplied evidence IDs; output candidate, cited facts, and uncertainties.
  - Acceptance: Unknown IDs, unsupported symbols, or uncited facts invalidate the result.
  - Verify: Recorded positive, no-opportunity, hallucination, and prompt-injection scenarios pass.

- [ ] **RC-046 — Implement Thesis Agent prompt and validator** `P0 · AI · 40 min`
  - Depends on: RC-018, RC-045.
  - Do: Produce one typed TradeIntent or explicit abstention with thesis, confidence, evidence, expiry, and invalidation conditions.
  - Acceptance: The agent cannot emit execution commands or bypass schema validation.
  - Verify: Scenario tests cover buy, sell/exit, abstain, malformed size, missing evidence, and oversized proposal.

- [ ] **RC-047 — Implement Skeptic prompt and validator** `P0 · AI · 35 min`
  - Depends on: RC-046.
  - Do: Attack the thesis for data quality, contradictory evidence, concentration, event risk, and invalidation weakness.
  - Acceptance: Output is a structured critique/advisory; it cannot directly approve, veto, or execute.
  - Verify: Tests confirm the risk kernel remains authoritative regardless of Skeptic wording.

- [ ] **RC-048 — Implement committee orchestration** `P0 · Backend · 45 min`
  - Depends on: RC-045–RC-047, RC-031, RC-032.
  - Do: Execute Scout → Thesis → Skeptic → Risk Kernel, append events after every step, and expose progress states.
  - Acceptance: A failed/invalid role stops safely or uses one bounded repair attempt; execution never begins on partial output.
  - Verify: Integration tests cover success, abstain, timeout, invalid JSON, provider error, and risk veto.

- [ ] **RC-049 — Add bounded repair and budget enforcement** `P0 · AI · 30 min`
  - Depends on: RC-044, RC-048.
  - Do: Permit at most one schema-repair call, enforce per-role timeout, maximum calls, and cost/token budget.
  - Acceptance: Exhaustion yields a recorded fail-closed state and readable UI message.
  - Verify: Fake provider forces each limit and asserts exact call counts.

- [ ] **RC-050 — Add prompt/model provenance** `P0 · AI · 25 min`
  - Depends on: RC-045–RC-048.
  - Do: Version prompt templates and record model ID, prompt version/hash, evidence IDs, latency, usage, and validation result.
  - Acceptance: Every AI event is reproducible enough to identify its configuration without storing chain-of-thought.
  - Verify: Exported Decision Card contains all provenance fields and no secret/system prompt content.

- [ ] **RC-051 — Add prompt-injection defenses** `P0 · Security · 35 min`
  - Depends on: RC-045–RC-048.
  - Do: Treat news/tool text as untrusted data, delimit evidence, restrict tools, validate all IDs, and reject instructions embedded in evidence.
  - Acceptance: Injection fixtures cannot alter policy, allowed tools, symbol universe, or output schema.
  - Verify: At least ten adversarial fixtures pass with zero execution attempts.

- [ ] **RC-052 — Add committee API and progress stream** `P0 · Backend · 35 min`
  - Depends on: RC-048.
  - Do: Add case-start, case-status, event-stream, approval/execution, and cancel endpoints with clear recorded/paper modes.
  - Acceptance: Duplicate starts are idempotent; disconnect/reconnect resumes from event sequence.
  - Verify: API tests cover authentication assumption, validation, idempotency, reconnect, and terminal states.

- [ ] **RC-053 — Build the 20-case evaluation dataset** `P0 · AI + Evaluation · 60 min`
  - Depends on: RC-021, RC-022, RC-051.
  - Do: Create balanced approve/resize/veto/abstain/error cases including stale data, concentration, duplicate intent, injection, missing evidence, and provider failure.
  - Acceptance: Each case has an expected schema and policy outcome; fixtures contain no copyrighted article bodies or secrets.
  - Verify: Dataset validator reports 20 valid, uniquely identified cases.

- [ ] **RC-054 — Run and freeze the AI evaluation baseline** `P0 · Evaluation · 45 min`
  - Depends on: RC-053.
  - Do: Run the full dataset and record schema validity, evidence validity, policy outcome, unauthorized executions, latency, usage, and cost.
  - Acceptance: Zero unauthorized executions and unknown evidence accepted; schema validity reaches 100% after bounded repair.
  - Verify: A single documented command regenerates machine-readable and Markdown reports.

### Gate 6 — Safe agentic behavior

- [ ] All 20 evaluation cases terminate with the expected safe outcome.
- [ ] AI roles have no execution authority and injection attempts cannot change policy.
- [ ] Every decision records model/prompt/evidence provenance without chain-of-thought.
- [ ] Commit checkpoint: `feat(agents): orchestrate bounded auditable trade committee`.

## Phase 6 — Judge-facing experience

- [ ] **RC-055 — Establish the visual system** `P0 · Design · 30 min`
  - Depends on: RC-004, RC-024.
  - Do: Define color, type, spacing, status semantics, icon use, focus states, and recorded/live badges. Use color plus text/icon, never color alone.
  - Acceptance: Approve, resize, veto, pending, error, recorded, and paper-live states are distinct and accessible.
  - Verify: Contrast check and visual review at desktop and narrow widths.

- [ ] **RC-056 — Build the case-opening view** `P0 · Frontend · 35 min`
  - Depends on: RC-052, RC-055.
  - Do: Show watchlist trigger, mode, market clock, account summary, and a single clear `Open case` action.
  - Acceptance: The first screen communicates paper-only operation and differentiated value within 15 seconds.
  - Verify: Two unfamiliar reviewers explain the product correctly before clicking.

- [ ] **RC-057 — Build the live committee timeline** `P0 · Frontend · 45 min`
  - Depends on: RC-052, RC-055.
  - Do: Stream Scout, Thesis, Skeptic, and Risk events with concise summaries, tool/provenance indicators, latency, and clear current state.
  - Acceptance: Reconnect does not duplicate events; animation respects reduced-motion preferences.
  - Verify: Component tests, reconnect test, reduced-motion check, and browser console check.

- [ ] **RC-058 — Build the evidence drawer** `P0 · Frontend · 35 min`
  - Depends on: RC-017, RC-057.
  - Do: Let viewers inspect source, observation time, symbol, summary, and hash/reference for every cited claim.
  - Acceptance: Unknown evidence renders as an explicit integrity error, not blank content.
  - Verify: Component tests cover fresh, stale, missing, recorded, and unsafe-HTML evidence.

- [ ] **RC-059 — Build proposed-vs-approved verdict view** `P0 · Frontend · 45 min`
  - Depends on: RC-031, RC-057.
  - Do: Show 8% proposed notional beside 2% approved notional, triggered rules, exact delta, or prominent veto reasons.
  - Acceptance: Resize/veto is the visual hero and requires no narration to understand.
  - Verify: Screenshot review at 1440×900 and 390×844; numeric formatting tests pass.

- [ ] **RC-060 — Build paper-order timeline and kill switch** `P0 · Frontend · 40 min`
  - Depends on: RC-042, RC-052.
  - Do: Display client order ID, safe Alpaca order reference, state transitions, timestamps, fill details, and a guarded kill switch.
  - Acceptance: Recorded fills are labeled; live paper orders are labeled; kill-switch state persists and blocks execution.
  - Verify: E2E tests cover successful fill, rejection, cancellation, disconnect, and kill-before-execute.

- [ ] **RC-061 — Build Decision Card replay/export** `P0 · Frontend · 40 min`
  - Depends on: RC-033, RC-034, RC-052.
  - Do: Add replay controls, event inspection, integrity status, and sanitized JSON download.
  - Acceptance: Export contains full decision provenance but excludes secrets, raw prompts, and chain-of-thought.
  - Verify: Download schema test and import/replay round-trip pass.

- [ ] **RC-062 — Add transparent limitations and safety copy** `P0 · Product · 25 min`
  - Depends on: RC-056–RC-061.
  - Do: Explain paper-only behavior, IEX feed limitation, simulation caveats, non-advice status, recorded-mode labeling, and absence of live trading.
  - Acceptance: Copy is visible at decision points, not buried only in legal text.
  - Verify: Search rendered pages for required phrases and review against Alpaca documentation.

- [ ] **RC-063 — Add loading, empty, and failure states** `P0 · Frontend · 40 min`
  - Depends on: RC-056–RC-061.
  - Do: Design market-closed, no opportunity, provider timeout, Alpaca failure, stale evidence, corrupt replay, and offline fallback states.
  - Acceptance: Every failure tells the viewer what happened and whether an order could have been placed.
  - Verify: Story/component coverage plus one E2E scenario per failure class.

- [ ] **RC-064 — Complete accessibility and responsive pass** `P0 · Frontend · 45 min`
  - Depends on: RC-055–RC-063.
  - Do: Ensure keyboard operation, focus visibility, semantic headings, labels, live-region restraint, contrast, reduced motion, and responsive layout.
  - Acceptance: Core demo is usable without a mouse and has no serious automated accessibility findings.
  - Verify: Axe/Playwright scan plus manual keyboard pass at desktop and mobile widths.

- [ ] **RC-065 — Prove the two-minute golden demo** `P0 · Product + QA · 45 min`
  - Depends on: RC-056–RC-064.
  - Do: Script and run resize, veto, and failure-fallback scenes; remove clicks and text that do not advance the story.
  - Acceptance: Five consecutive complete runs succeed; primary product flow stays under two minutes.
  - Verify: Record timestamps and results in `docs/evidence/demo-rehearsal.md`.

### Gate 7 — Judge-ready product

- [ ] A first-time viewer understands proposal, objection, verdict, and outcome without narration.
- [ ] Five consecutive golden demos pass, including one network-disabled run.
- [ ] Accessibility, mobile layout, browser console, and failure states are clean.
- [ ] Commit checkpoint: `feat(ui): deliver judge-facing RiskCourt experience`.

## Phase 7 — Evaluation, hardening, and deployment

- [ ] **RC-066 — Create the reproducible evaluation command** `P0 · Evaluation · 35 min`
  - Depends on: RC-054.
  - Do: Add one command that validates fixtures, runs the 20 cases, aggregates metrics, and writes JSON/Markdown outputs.
  - Acceptance: A clean checkout regenerates the report without editing source or requiring live trading.
  - Verify: Delete generated report, rerun command, and confirm only expected deterministic fields change.

- [ ] **RC-067 — Add end-to-end retry/idempotency tests** `P0 · QA · 35 min`
  - Depends on: RC-030, RC-041, RC-052.
  - Do: Exercise double-click, HTTP retry, worker restart, stream reconnect, and duplicate webhook/update behavior.
  - Acceptance: Every case produces at most one Alpaca submission and one execution record.
  - Verify: Automated test asserts unique client order IDs and call count of one.

- [ ] **RC-068 — Run a security review** `P0 · Security · 45 min`
  - Depends on: Gate 7.
  - Do: Review secret handling, tool permissions, input validation, injection, CORS, unsafe HTML, logs, exports, dependency advisories, and live-trading absence.
  - Acceptance: No unresolved high-severity issue; medium issues have mitigation or documented acceptance.
  - Verify: Secret scan, dependency audit, adversarial tests, and manual configuration review are recorded.

- [ ] **RC-069 — Add observability and health endpoints** `P0 · DevOps · 30 min`
  - Depends on: RC-052.
  - Do: Add liveness/readiness, mode/provider dependency status, structured redacted logs, request/case IDs, and latency/error counters.
  - Acceptance: Health output reveals no secrets/account balances and distinguishes degraded recorded fallback from paper-ready state.
  - Verify: Tests cover healthy, missing provider, missing Alpaca, database failure, and recorded-only states.

- [ ] **RC-070 — Deploy the backend safely** `P0 · DevOps · 45 min`
  - Depends on: RC-008, RC-068, RC-069.
  - Do: Configure paper/model secrets server-side, database persistence, allowed frontend origin, startup command, health check, and no live flags.
  - Acceptance: Hosted health is green; recorded mode remains available; logs contain no credentials.
  - Verify: Restart deployment, run health/API smoke, inspect startup logs, and attempt rejected live configuration.

- [ ] **RC-071 — Deploy the frontend** `P0 · DevOps · 35 min`
  - Depends on: RC-008, RC-070.
  - Do: Configure hosted backend URL, production build, routing fallback, security headers where supported, and cache policy.
  - Acceptance: An incognito visitor can run the recorded golden path with no login.
  - Verify: Desktop/mobile/incognito smoke plus browser console/network inspection.

- [ ] **RC-072 — Run hosted full-story verification** `P0 · QA · 45 min`
  - Depends on: RC-070, RC-071.
  - Do: Exercise recorded resize, recorded veto, offline/failure fallback, live paper read, kill switch, replay/export, and tiny-order path when appropriate.
  - Acceptance: Hosted results match local behavior and every external dependency failure fails closed.
  - Verify: Complete `docs/evidence/hosted-verification.md` with timestamp, deployment identifiers, and sanitized screenshots.

### Gate 8 — Release candidate

- [ ] Evaluation report is reproducible and all safety targets are green.
- [ ] Security review has no unresolved high-severity finding.
- [ ] Hosted app passes incognito desktop/mobile and recorded/live-paper checks.
- [ ] Commit checkpoint: `chore(release): verify hosted hackathon candidate`.

## Phase 8 — Submission package

- [ ] **RC-073 — Write the public README** `P0 · Product · 45 min`
  - Depends on: Gate 8.
  - Do: Lead with GIF/image, pitch, demo link, paper-only disclaimer, architecture, Alpaca component mapping, recorded-first setup, evaluation, limitations, team, and MIT license.
  - Acceptance: A judge can understand and run recorded mode without reading source.
  - Verify: Follow setup from a clean clone and click every README link while logged out.

- [ ] **RC-074 — Produce cover image and screenshots** `P0 · Design · 45 min`
  - Depends on: Gate 7.
  - Do: Create one recognizable cover and 3–5 consistent screenshots showing debate, resize/veto, Alpaca order, and Decision Card.
  - Acceptance: Images remain legible at LabLab thumbnail and slide sizes and disclose recorded data where applicable.
  - Verify: Preview exports at actual target dimensions and compress without visible degradation.

- [ ] **RC-075 — Record and edit the 2–3 minute video** `P0 · Product · 90 min`
  - Depends on: RC-065, RC-072.
  - Do: Follow hook → problem → live behavior → technical proof → business value → results. Use the verified release candidate.
  - Acceptance: Product appears in first 15 seconds; Alpaca proof and risk differentiation are visible; captions are included; no credential/account-sensitive data appears.
  - Verify: Two outsiders watch once and correctly state problem, differentiation, and proof.

- [ ] **RC-076 — Create the 6–8 slide deck** `P0 · Product · 60 min`
  - Depends on: RC-074, RC-075.
  - Do: Build hook, problem, workflow, result, architecture, evaluation, business value, and links/team slides.
  - Acceptance: Deck tells the same story and uses the same metrics/version as the app, README, and video.
  - Verify: Run a consistency check on all names, URLs, metric values, and disclaimers.

- [ ] **RC-077 — Draft all LabLab fields** `P0 · Product · 45 min`
  - Depends on: RC-073–RC-076.
  - Do: Draft title, short description, long description, technology/category tags, repository, demo, video, slide, and team fields in `docs/SUBMISSION_COPY.md`.
  - Acceptance: Copy maps explicitly to all four judging dimensions without unsupported performance claims.
  - Verify: Compare field-by-field with the live submission form and organizer requirements.

- [ ] **RC-078 — Freeze and tag the submission candidate** `P0 · Git · 25 min`
  - Depends on: RC-077.
  - Do: Run full verification, fix only blockers, record commit SHA, and create the requested release tag only when authorized.
  - Acceptance: Working tree is clean and all assets point to the same frozen version.
  - Verify: `git status --short`, full verification command, and logged-out link check all pass.

- [ ] **RC-079 — Submit with buffer** `P0 · User · 30 min`
  - Depends on: RC-078.
  - Do: Submit several hours before the confirmed cutoff; do not wait for end-of-day assumptions.
  - Acceptance: LabLab shows a completed submission and provides a public/preview page or confirmation.
  - Verify: Reopen the submission page in an incognito browser and confirm every required field/link/media item.

- [ ] **RC-080 — Preserve final evidence and stop mutating** `P0 · User + Git · 20 min`
  - Depends on: RC-079.
  - Do: Record submission time, URL, commit SHA, deployment IDs, and final link-check result. Make no post-submit changes unless the platform explicitly permits edits and a blocking defect exists.
  - Acceptance: `docs/SUBMISSION_RECORD.md` distinguishes local, hosted, repository, and platform-submission evidence.
  - Verify: Another person can trace the submitted artifact to the exact commit and hosted version.

## P1 stretch queue — only after Gate 8

- [ ] **P1-01 — Add a policy editor with safe presets**
  - Build only if the fixed policy is already fully tested. Prevent settings outside demo-safe bounds.

- [ ] **P1-02 — Add counterfactual shadow outcome**
  - Compare the original proposal with the resized/vetoed decision using clearly historical/recorded prices; do not imply causation or guaranteed avoided loss.

- [ ] **P1-03 — Add portfolio-level risk visualization**
  - Visualize gross exposure, concentration, daily loss budget, and pending-order consumption.

- [ ] **P1-04 — Add Decision Card PDF export**
  - Keep JSON as the canonical artifact; PDF is presentation-only and must retain provenance/disclaimers.

- [ ] **P1-05 — Add read-only judge mode**
  - Provide preloaded cases and hide controls that require credentials or mutate paper state.

- [ ] **P1-06 — Add a second model/provider adapter**
  - Use for resilience only if it does not complicate evaluation or provenance.

- [ ] **P1-07 — Add richer event-trigger selection**
  - Add one additional trigger type only if it strengthens the same courtroom demo.

- [ ] **P1-08 — Add lightweight usage/cost dashboard**
  - Show per-case latency, calls, tokens, and estimated cost without exposing provider internals.

## P2 post-hackathon backlog

- Options and crypto support.
- Multi-broker execution adapters.
- Production authentication, tenancy, and role-based policy administration.
- Durable managed database and object storage.
- Formal compliance review and retention policies.
- Human approval workflows and multi-party authorization.
- Broader backtesting, walk-forward evaluation, and market-impact modeling.
- Live-money readiness assessment; this requires a separate security, regulatory, and operational program and is not implied by the hackathon build.

## Final “prize-ready” checklist

- [ ] The differentiated behavior is visible within 15 seconds.
- [ ] Resize/veto, not prediction accuracy, is the demo hero.
- [ ] Alpaca MCP, Trading API, CLI, and paper environment each have visible, truthful proof.
- [ ] A real paper-order artifact links RiskCourt to the Alpaca dashboard.
- [ ] Zero hard policy violations reach execution in the evaluation set.
- [ ] Zero duplicate paper orders occur under retry/restart tests.
- [ ] Unknown, stale, or injected evidence always fails closed.
- [ ] Recorded mode works with the network disabled and is unmistakably labeled.
- [ ] Five consecutive two-minute demos pass.
- [ ] Hosted app passes incognito desktop and mobile checks.
- [ ] Repository setup works from a clean clone.
- [ ] README, app, video, slides, and LabLab copy use identical facts and metrics.
- [ ] No secret, account-sensitive detail, chain-of-thought, or unsupported financial claim is public.
- [ ] Submission is tied to an exact commit and deployment.
- [ ] Submission is verified on LabLab before the authoritative cutoff.
