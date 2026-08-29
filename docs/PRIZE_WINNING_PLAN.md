# Alpaca AI Trading Agents Hackathon — Prize-Winning Plan

**Working title:** RiskCourt

**Tagline:** The AI trading desk that argues before it acts.

**Build window:** August 29–September 4, 2026

**Mode:** Alpaca paper trading only; no live-money path in the hackathon build.

**Planning assumption:** One primary builder, with a second person helping with design, testing, or the submission if available.

> A prize cannot be guaranteed. This plan is deliberately optimized for the published judging criteria and for a memorable, reliable live demo rather than broad feature count.

## 1. Event contract

The current LabLab page describes a seven-day, fully online hackathon running August 28–September 4, 2026. The challenge is to build an autonomous trading agent or trading application on Alpaca using its Trading API, MCP server, CLI, and paper environment.

Published submission components:

- Project title, short description, long description, and technology/category tags.
- Cover image, video presentation, and slide presentation.
- Public GitHub repository, demo platform, and application URL.
- Team size of 1–6 people; registration on both LabLab and its Discord is expected.
- Original work with MIT-compatible submission terms.

Published judging dimensions:

1. **Application of Technology** — effective model and platform integration.
2. **Presentation** — clarity and effectiveness of the project story.
3. **Business Value** — practical impact and fit with real business needs.
4. **Originality** — novelty and demonstrated behavior.

### Open organizer questions

- **Prize discrepancy:** the live page header currently says `$6,000`, while LabLab's expanded indexed prize section lists `$5,000` split into `$2,500 / $1,500 / $1,000`. Confirm the authoritative amount in the enrolled dashboard or Discord. This does not change the build plan.
- Confirm the exact submission cutoff time and timezone; do not assume end-of-day on September 4.
- Confirm whether every project must use all three of Trading API, MCP, and CLI, or whether any part of that stack is sufficient. The proposed architecture uses all three meaningfully.
- Confirm any sponsor-specific branding, disclosure, demo, or repository requirements announced at kickoff.

Sources: [LabLab event page](https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon), [Alpaca Trading MCP](https://docs.alpaca.markets/us/docs/alpaca-mcp-server), [Alpaca CLI](https://docs.alpaca.markets/us/docs/alpacas-cli), and [Alpaca paper trading](https://docs.alpaca.markets/us/docs/paper-trading).

## 2. The winning product thesis

Most teams will build some variation of `market data → sentiment/technical analysis → buy or sell`. That is easy to understand but difficult to distinguish.

**RiskCourt is an auditable AI risk desk for autonomous paper trading.** A Scout finds an opportunity, a Thesis Agent proposes a structured trade, and a Skeptic attacks the thesis. A deterministic Risk Kernel then vetoes, resizes, or approves the order. Only an approved order can reach Alpaca paper trading. Every claim, objection, rule, tool call, and order update becomes a replayable Decision Card.

The memorable behavior is not merely that the AI trades. It is that the audience can watch the system disagree with itself, prevent an unsafe action, and explain the final decision.

### One-sentence pitch

RiskCourt makes autonomous trading inspectable: multiple AI agents debate each trade, a non-AI risk kernel has the final veto, and Alpaca executes only policy-compliant orders in paper trading.

### Target customer

The initial customer is a fintech, registered investment adviser technology team, or trading-platform product team exploring agentic workflows but unable to accept a black-box model with unrestricted order access.

### Core promise

`No trade without evidence. No order without deterministic risk approval. No decision without a replayable audit trail.`

## 3. Judge strategy

| Criterion | What judges see | Proof in the submission |
|---|---|---|
| Application of Technology | Alpaca market/account context flows through MCP; paper orders and trade updates use the Trading API; CLI powers schema checks, dry-run previews, and a reproducible demo script; the model produces typed arguments rather than prose commands. | Architecture slide, live tool timeline, real paper-order ID, CLI transcript, integration tests. |
| Presentation | A visual courtroom-style debate culminates in a clear approve/resize/veto verdict and a live paper order. | A 90-second golden-path demo plus a 30-second failure/recovery scene. |
| Business Value | Risk controls, separation of duties, evidence, and auditability address the main blocker to adopting autonomous financial agents. | Customer slide, risk policy editor, Decision Card export, measurable safety results. |
| Originality | The hero is the agent that refuses or safely modifies trades, not another generic prediction bot. | Side-by-side proposed vs. approved order, adversarial replay, counterfactual shadow outcome. |

## 4. Scope

### Must ship

- A curated universe of 5–10 highly liquid US equities; no unrestricted symbol discovery in the MVP.
- Alpaca paper account, positions, clock, bars/quotes, movers, and news available to the research loop.
- A typed `TradeIntent` containing symbol, side, quantity/notional, order type, time in force, confidence, thesis, evidence references, invalidation conditions, and expiry.
- Three visible reasoning roles: Scout, Thesis Agent, and Skeptic.
- A deterministic Risk Kernel with hard vetoes and resizing rules.
- Paper execution with idempotent client order IDs and a global kill switch.
- Real-time order-status updates and a persistent, replayable Decision Card.
- A polished dashboard with a single-click seeded demo when markets, APIs, or the model are unavailable.
- An evaluation report covering safety, reliability, latency, and an honest statement of paper-trading limitations.
- Public MIT-licensed repository, deployed demo, short video, slides, cover image, and complete LabLab entry.

### Explicitly cut

- Live-money trading or a UI control that can enable it.
- Options, crypto, multi-broker support, social trading, user billing, mobile apps, and production authentication.
- Training a prediction model from scratch.
- Claims of profitable performance or financial advice.
- A sprawling swarm of agents. Three model roles plus deterministic risk and execution is enough to tell the story.
- High-frequency trading. Alpaca itself cautions that its platform is not intended for HFT-style latency requirements.

## 5. Golden demo

The demo should take under two minutes and work identically from a seeded fixture or live Alpaca data.

1. The dashboard receives a news or price-movement trigger for a watchlisted symbol.
2. Scout opens a case and shows cited market/account evidence.
3. Thesis Agent proposes a paper trade at 8% portfolio notional.
4. Skeptic identifies concentration, stale-news, and downside risks.
5. Risk Kernel visibly resizes the order to the 2% cap, attaches an exit plan, or vetoes it.
6. The user enables autonomous paper mode; an approved order executes through Alpaca with a unique client order ID.
7. The live order status moves from submitted to accepted/filled (or a deterministic simulated fill is used if the market is closed).
8. The Decision Card replays the complete path and compares the approved action with the rejected original proposal.
9. End on the trust message: **“The model can propose. Policy decides what capital is allowed to do.”**

Also record a failure path: corrupt or stale evidence causes a fail-closed veto, not a silent retry or unsafe order.

## 6. Architecture

### Recommended stack

- **Frontend:** React, TypeScript, Vite, Tailwind CSS, and Recharts.
- **Backend:** Python 3.12, FastAPI, Pydantic, SQLAlchemy/SQLite, and `alpaca-py`.
- **AI:** one structured-output-capable model behind a provider interface; pin the selected model in configuration and capture model/prompt versions in every decision.
- **Alpaca:** official Trading MCP server for agent-accessible research tools; Trading API/`alpaca-py` for paper execution and trade-update streaming; Alpaca CLI for `doctor`, schema inspection, `--dry-run`, and scripted verification.
- **Testing:** pytest for risk/orchestration, Vitest for frontend logic, Playwright for the golden path, and recorded fixtures for offline replay.
- **Deployment:** static frontend plus a Python web service that supports WebSockets. Select providers on Day 1 based on credentials already available; do not leave hosting until submission day.

### Component flow

```text
Alpaca market/account/news tools
             |
             v
      Evidence Snapshot
             |
             v
Scout -> Thesis Agent -> Skeptic
             |
             v
       Typed TradeIntent
             |
             v
 Deterministic Risk Kernel -----> Veto + reasons
             |
          Approve/resize
             |
             v
 Paper Execution Adapter -> Alpaca order/trade updates
             |
             v
  Append-only Decision Events -> Dashboard + Replay + Export
```

### Separation of authority

- Research roles receive read-only MCP toolsets.
- Model output can never call the execution endpoint directly.
- Risk validation occurs server-side after model output and immediately before execution.
- The executor accepts only a signed/hashed, unexpired approval result linked to the current portfolio snapshot.
- Paper mode is forced in code and asserted at startup. A production/live endpoint is absent rather than hidden.

### Initial risk policy

- Allowed symbols: explicit watchlist only.
- Maximum new position: 2% of current equity.
- Maximum total gross exposure: 20% of current equity.
- Maximum one-day realized/unrealized loss before kill switch: 1%.
- Maximum three open positions and one pending order per symbol.
- Reject market/account evidence older than 60 seconds for live decisions.
- Reject a trade lacking at least two independent evidence items and an invalidation condition.
- Reject duplicate intents by deterministic intent hash; use an Alpaca client order ID for idempotency.
- Reject trading when account/market status is uncertain, an upstream call fails, or policy evaluation errors.
- Use bracket/exit logic where supported; otherwise record why and fail closed when an exit cannot be represented safely.

These limits are demo safety controls, not investment advice or a claim that the strategy is suitable for live trading.

## 7. Data contracts that prevent build drift

```text
EvidenceItem
  id, type, source, symbol, observed_at, payload_hash, summary, raw_reference

TradeIntent
  id, symbol, side, notional, order_type, time_in_force, confidence,
  thesis, evidence_ids[], invalidation_conditions[], expires_at, model_version

RiskVerdict
  intent_id, outcome[approve|resize|veto], approved_notional,
  triggered_rules[], reason, portfolio_snapshot_hash, expires_at

DecisionEvent
  case_id, sequence, actor, event_type, timestamp, input_hash,
  output, tool_name, latency_ms, success

ExecutionRecord
  case_id, intent_id, client_order_id, alpaca_order_id, status,
  submitted_at, filled_at, filled_qty, filled_avg_price
```

The append-only event stream is the source of truth. Current UI state is derived from events so every demo can be replayed and audited.

## 8. Dated build plan

### Saturday, August 29 — Lock the story and make failure impossible to hide

- Create the architecture skeleton, typed contracts, secret-safe configuration, paper-mode assertion, and fixture format.
- Build the static courtroom dashboard shell and storyboard the exact demo before integrating APIs.
- Capture two historical/seeded cases: one approved-after-resize and one veto.
- Exit criterion: the entire demo can be clicked through with fixtures and no external dependency.

### Sunday, August 30 — Build the decision engine before the model layer

- Implement the deterministic Risk Kernel and comprehensive table-driven tests.
- Implement the append-only decision-event store and replay API.
- Add the global kill switch, duplicate-intent protection, stale-data rejection, and approval expiry.
- Exit criterion: adversarial tests cannot bypass a hard limit; replay is deterministic.

### Monday, August 31 — Integrate Alpaca while US markets are open

- Connect paper account/positions/clock and IEX market data; document IEX-only limitations.
- Connect the official MCP server with read-only research toolsets.
- Add paper order submission and trade-update streaming through Alpaca's Trading API.
- Add CLI health, schema, and dry-run checks.
- Exit criterion: one tiny, policy-compliant paper order completes end to end and is visible in both RiskCourt and the Alpaca dashboard.

### Tuesday, September 1 — Add bounded AI reasoning

- Implement Scout, Thesis, and Skeptic prompts with strict structured output and evidence IDs.
- Reject hallucinated evidence IDs and malformed/expired intents.
- Capture prompt/model/tool versions and latency in Decision Events.
- Run at least 20 recorded/adversarial scenarios.
- Exit criterion: 100% schema-valid final intents after bounded retry, zero unauthorized orders, and no uncited claim reaching execution.

### Wednesday, September 2 — Polish the wow moment and prove reliability

- Finish live debate animation, proposal-vs-verdict diff, order timeline, replay, and exportable Decision Card.
- Add offline demo mode with a highly visible `Recorded scenario` badge.
- Add performance/risk charts and a paper-trading limitations panel.
- Run unit, integration, UI, and browser smoke tests from a clean checkout.
- Exit criterion: five consecutive golden-path demos succeed without manual repair.

### Thursday, September 3 — Deploy and produce the submission

- Deploy frontend/backend; verify secrets are server-side and paper mode is enforced in the hosted environment.
- Record the video before final copy polishing: hook, problem, live behavior, architecture, proof, business value.
- Build 6–8 slides and a cover image from the same visual system.
- Draft all LabLab fields and ask two outsiders to repeat back the value proposition after viewing the video.
- Exit criterion: public URL, public MIT repository, video, slides, and all written fields are ready one full day early.

### Friday, September 4 — Freeze, rehearse, and submit early

- Recheck the organizer dashboard for the exact cutoff and any changed requirements.
- Run the hosted smoke test and one live-market demonstration during market hours if feasible.
- Tag the submission commit and record its SHA in the submission notes.
- Submit with a multi-hour buffer, then verify every link from an incognito browser.
- Do not add features after the freeze; fix only submission-blocking defects.

## 9. Atomic build checklist

- [ ] **1. Establish repository and demo contracts**
  - What to build: project skeleton, environment example, paper-only startup check, typed core models, fixture schema, and decision log.
  - Acceptance: app boots without secrets in recorded mode; live mode refuses to boot if paper configuration is not provable.
  - Verify: backend unit tests plus secret scan.

- [ ] **2. Create the fixture-first golden path**
  - What to build: two deterministic cases and a static end-to-end dashboard path.
  - Acceptance: approve/resize and veto stories can both be demonstrated offline with a visible provenance badge.
  - Verify: Playwright test with network disabled.

- [ ] **3. Implement the deterministic Risk Kernel**
  - What to build: allowlist, exposure, loss, staleness, evidence, duplicate, expiry, and fail-closed rules.
  - Acceptance: each rule has allow, resize, and/or veto coverage; model text cannot override policy.
  - Verify: parameterized pytest suite including malformed and adversarial intents.

- [ ] **4. Implement audit storage and replay**
  - What to build: append-only Decision Events, case projection, JSON export, and replay API.
  - Acceptance: replay produces the same verdict and event order from an exported case.
  - Verify: round-trip and tamper-detection tests.

- [ ] **5. Add read-only Alpaca context**
  - What to build: account, positions, clock, bars/quotes, movers, and news adapters using MCP/API as appropriate.
  - Acceptance: every evidence item has source, timestamp, symbol, and payload hash; stale data is rejected.
  - Verify: contract tests against recorded responses and one live paper-account smoke.

- [ ] **6. Add safe paper execution**
  - What to build: approval token/hash validation, idempotent client order IDs, paper order submission, cancellation, and order updates.
  - Acceptance: only current approved/resized intents execute; duplicate submission returns the original record.
  - Verify: tiny-order paper smoke plus mocked partial-fill, reject, timeout, and retry cases.

- [ ] **7. Add Alpaca CLI verification**
  - What to build: documented `doctor`, schema, dry-run, and account/order inspection commands used by the demo and CI/manual checks.
  - Acceptance: CLI output can be tied to the same paper account and client order ID without exposing credentials.
  - Verify: sanitized transcript committed under demo evidence.

- [ ] **8. Add the three AI roles**
  - What to build: constrained prompts, structured results, evidence-ID validation, bounded retries, and provider abstraction.
  - Acceptance: no free-form order reaches risk evaluation; unknown evidence IDs fail closed.
  - Verify: at least 20 recorded scenarios and prompt-injection cases.

- [ ] **9. Finish the judge-facing UI**
  - What to build: live debate, evidence drawer, proposal/verdict diff, status timeline, replay, metrics, and kill switch.
  - Acceptance: a first-time viewer can identify proposal, objection, verdict, and outcome without narration.
  - Verify: five-person hallway test or two-person minimum, accessibility audit, and browser smoke.

- [ ] **10. Create the evaluation report**
  - What to build: safety-rule pass rate, schema validity, duplicate prevention, tool success, latency, and paper limitations.
  - Acceptance: all metrics are reproducible from a script and none imply live profitability.
  - Verify: clean run produces the checked-in report from fixtures.

- [ ] **11. Deploy and verify the full story**
  - What to build: hosted frontend/backend, health status, recorded fallback, monitoring, and safe configuration.
  - Acceptance: incognito visitor completes the golden path; no secret or live-trading switch is client-visible.
  - Verify: end-to-end hosted smoke and manual mobile/desktop pass.

- [ ] **12. Package and submit**
  - What to build: README, architecture diagram, MIT license, 2–3 minute video, 6–8 slides, cover image, LabLab copy, and exact links.
  - Acceptance: every required field is complete, every link works logged out, and the submission points to the frozen commit.
  - Verify: two-person submission checklist and post-submit re-open.

## 10. Evaluation scorecard

The project is submission-ready only when all gates are green:

| Gate | Target |
|---|---|
| Hard policy violations that reach execution | 0 |
| Duplicate orders in retry tests | 0 |
| Unknown or uncited evidence accepted | 0 |
| Schema-valid agent outputs after bounded retry | 100% of evaluation set |
| Golden-path demo success | 5 consecutive runs |
| Offline fallback success with network disabled | 100% |
| Decision replay round-trip | Exact event/verdict match |
| Hosted secret exposure | 0 findings |
| Demo duration | Under 2 minutes for product flow |
| Public link check | All links pass logged out |

Paper P&L may be shown as an outcome, but it is not a quality gate. Alpaca notes that paper simulation omits market impact, latency slippage, queue position, regulatory fees, and other live-market effects.

## 11. Submission narrative

### Video outline (2–3 minutes)

- **0:00–0:15 — Hook:** “Would you give an LLM a brokerage key? Neither would we.” Show a reckless 8% trade proposal.
- **0:15–0:40 — Problem:** autonomous agents are powerful, but black-box reasoning and unrestricted execution are adoption blockers.
- **0:40–1:35 — Live demo:** evidence, debate, risk resize/veto, paper execution, Alpaca order ID, and replay.
- **1:35–2:00 — Technical proof:** MCP tool boundary, deterministic kernel, Trading API updates, CLI verification, append-only audit.
- **2:00–2:25 — Business value:** governance layer for fintech agent workflows; policy and audit make pilots safer.
- **2:25–2:40 — Close:** safety results and the one-line promise.

### Slide outline

1. Hook and product promise.
2. Why autonomous trading agents need a control plane.
3. The RiskCourt workflow.
4. Live Decision Card/result.
5. Alpaca + AI architecture and separation of authority.
6. Evaluation evidence and paper-trading caveats.
7. Customer value and expansion path.
8. Team, repository, and demo QR/link.

### README proof order

1. 10-second GIF or screenshot of proposal → resize/veto → order.
2. One-sentence value proposition and recorded demo link.
3. Safety disclaimer and paper-only statement.
4. Architecture diagram and why each Alpaca component is used.
5. Reproducible setup with recorded mode first, live paper mode second.
6. Evaluation results, limitations, and roadmap.
7. License and contributor credits.

## 12. Risks and pivots

| Risk | Early signal | Pivot |
|---|---|---|
| Alpaca MCP integration consumes too much time | No stable read-only call by Monday noon | Keep the MCP proof as a separate verified adapter/demo path; use direct API fixtures for the product flow and disclose the boundary. |
| Market closed or no fill during judging | Demo depends on immediate live fill | Make submitted/accepted a valid live endpoint and use a clearly labeled recorded fill for the complete replay. |
| Free IEX feed is too sparse | Quotes diverge or triggers are weak | Curate liquid symbols, use historical bars/news, and explain the IEX-only constraint. |
| Model latency or provider outage | Case takes over 30 seconds | Cache evidence, parallelize only read-only research, cap retries, and switch to the recorded scenario visibly. |
| UI polish falls behind | Core flow is still CLI-only on September 2 | Cut charts and settings; protect the debate, verdict diff, order status, and replay views. |
| Strategy looks financially unconvincing | Reviewers ask about returns first | Recenter on governance and operational safety; show reproducible safety metrics, not cherry-picked P&L. |
| Requirements change | Discord/dashboard announcement differs from this document | Update the event contract first, then re-rank tasks; preserve the core demo unless it becomes ineligible. |

## 13. Decisions needed within the first two hours

1. Confirm team size and owner for backend, frontend/design, evaluation, and submission.
2. Confirm available AI provider/API budget and select one structured-output-capable model.
3. Create/verify an Alpaca paper account; never paste API keys into chat, issues, logs, screenshots, or the repository.
4. Enroll on LabLab and Discord, then record the exact deadline and any sponsor clarifications.
5. Approve the RiskCourt concept or replace it before implementation begins. After approval, freeze the core promise and cut new ideas aggressively.

## 14. Definition of “prize-ready”

This is not “the code runs.” It means:

- A judge understands the differentiated value in under 15 seconds.
- The complete behavior is visible, not hidden in terminal logs or architecture claims.
- A real Alpaca paper-order artifact proves integration.
- Deterministic tests prove that the model cannot bypass policy.
- Recorded mode makes the demo resilient without pretending that fixtures are live.
- The public repository, hosted app, video, slides, and LabLab page tell the same story.
- Every financial-performance statement is appropriately qualified.
- The submission is complete and independently link-checked before the organizer deadline.
