# Detailed Plan: Jev-Informed Pandas Tutor Evidence Workflow for RiskCourt

## Document status

- **Document type:** implementation plan only; no implementation is included in this file.
- **Created on:** 2026-09-25.
- **Repository:** `alpaca-ai-trading-agents-hackathon` / RiskCourt.
- **Working branch:** `codex/jev-detailed-repo-plans-20260925`.
- **Baseline commit observed:** `884818a` (`feat: provide deterministic forecast context to Jev`).
- **Pre-existing working-tree change:** `frontend/src/App.tsx` is modified before this plan work and must remain untouched by the planned package.
- **Requested outcome:** make RiskCourt's Jev/TypeSafe forecast, calibration, risk, approval, execution, and audit data easier to inspect with small, sanitized Pandas Tutor examples without adding a data-analysis dependency to the trading path.
- **Jev execution status:** the Jev UserPromptSubmit judgment was not present in this session. The TypeSafe console was not reachable because it presented a security-verification page, and no local TypeSafe API key or CLI was available. This plan is therefore derived from repository evidence and TypeSafe's documented typed-question model; it must not be described as a live Jev response or provider verification.

## 1. Purpose and safety position

RiskCourt already separates provider judgments from deterministic aggregation, risk policy, approvals, execution, persistence, and recorded fallback. That separation is the central safety property to preserve.

Pandas Tutor should be used only as a read-only visual explanation layer for sanitized tables. It can help a reviewer understand:

- how three juror forecasts become calibrated contributions;
- how calibration and confidence become weights;
- how disagreement produces `ready` versus `abstain`;
- how an option-implied hurdle and minimum edge are compared;
- how approved quantities and maximum loss remain code-owned;
- how provider provenance and fallback reasons are summarized after the fact.

It must never:

- call Alpaca;
- submit, cancel, or modify an order;
- read credentials or live account data;
- decide whether an order is executable;
- replace the kill switch, approval artifact, risk limits, or deterministic exit logic;
- transform a recorded fixture into evidence of live paper performance.

The desired architecture is:

```text
recorded fixture or explicitly sanitized export
        |
        |  remove account/order/provider-sensitive fields
        v
Pandas Tutor inspection snippet
        |
        |  explain deterministic calculations and audit joins
        v
RiskCourt tests and operator review
        |
        |  optional provider observation, separately gated
        v
Jev/TypeSafe shadow or active juror result
        |
        v
deterministic aggregation -> risk policy -> explicit approval -> paper adapter
```

## 2. Scope

### In scope

- A documented, repeatable Pandas Tutor workflow for RiskCourt's forecast and audit tables.
- Synthetic fixtures that mirror domain fields without exposing credentials, account IDs, order IDs, raw market references, or personal data.
- Inspection of deterministic probability aggregation, calibration, disagreement, edge, sizing, and provenance.
- A typed Jev/TypeSafe review contract for evidence quality and redaction checks, if later implemented.
- Recorded-mode and mock-provider verification gates.
- A clear boundary between analysis-only artifacts and execution-authorizing state.

### Out of scope

- Adding pandas to the RiskCourt backend or frontend runtime solely for visualization.
- Uploading raw provider state, Alpaca responses, account balances, market feeds, order references, or logs to a hosted visualizer.
- Changing the existing `typesafe_state.py`, `typesafe_provider.py`, `probability_engine.py`, risk limits, approval flow, or paper adapter in this documentation package.
- Enabling live trading, submitting a paper order, or changing a user account.
- Treating a Jev probability, confidence, or calibration score as an authorization to execute.
- Comparing real strategy performance using incomplete or unredacted data.
- Editing the pre-existing `frontend/src/App.tsx` change.

## 3. Repository facts to preserve

The plan is based on the current RiskCourt structure:

- `backend/src/riskcourt/typesafe_state.py` defines sanitized, role-scoped TypeSafe state and rejects sensitive state keys.
- `backend/src/riskcourt/typesafe_provider.py` owns the bounded provider adapter, provider response validation, question construction, and shadow metadata.
- `backend/src/riskcourt/typesafe_calibration.py` stores code-owned calibration observations for recorded TypeSafe evaluations.
- `backend/src/riskcourt/probability_engine.py` deterministically aggregates a complete jury and abstains on incomplete juries, zero weight, or excessive disagreement.
- `backend/src/riskcourt/strategy_math.py` owns calibration shrinkage, weighted jury probability, option-implied hurdle, edge, maximum loss, and defined-risk sizing.
- Domain contracts in `backend/src/riskcourt/domain.py` require bounded probabilities, future forecast horizons, evidence IDs, invalidation text, approval bindings, and execution-specific invariants.
- Recorded mode must run without credentials; paper mode requires paper credentials; live configuration must fail closed.
- The personal workstation persists watchlists, scans, decisions, approvals, orders, positions, journal entries, kill-switch state, and audit history/export.
- Existing tests cover provider state, provider parsing, calibration, settings, probability aggregation, personal store/API, and risk limits.
- The repository's detailed TODO and release documents distinguish local recorded evidence from official paper-account, hosted, and submission evidence.

The inspection workflow must strengthen these boundaries rather than create a parallel source of truth.

## 4. Desired deliverables

| ID | Deliverable | Intended location | Required property |
|---|---|---|---|
| D1 | This plan | `docs/PLAN_JEV_PANDASTUTOR_RISKCOURT.md` | Full repository-specific sequence and gates |
| D2 | Juror aggregation visualizer example | Proposed `docs/examples/` or agreed developer-tools location | Synthetic, self-contained, no network |
| D3 | Edge and sizing visualizer example | Same agreed location | Shows formulas without execution side effects |
| D4 | Provenance/fallback summary example | Same agreed location | Separates provider result from deterministic result |
| D5 | Redaction contract/checklist | Documentation or helper module if implementation is authorized | Proves sensitive fields are excluded |
| D6 | Automated tests for any helper | `backend/tests/` | No network, no secrets, no state mutation |
| D7 | Verification/evidence record | Review/PR description or approved evidence file | Local/provider/paper/hosted evidence remain distinct |

No deliverable beyond D1 should be implemented until this plan is reviewed and the user authorizes the package.

## 5. Proposed inspection frames

### 5.1 Forecast frame

Use synthetic rows with only the fields needed to explain deterministic math:

- `case_id` replaced by a synthetic label such as `case_fixture_01`;
- `juror_id` using stable non-secret labels such as `juror_market`, `juror_catalyst`, and `juror_volatility`;
- `outcome`;
- `probability`;
- `calibration_score`;
- `confidence_stake`;
- `produced_at` and `horizon_at` using fixed UTC timestamps;
- `evidence_count` rather than evidence IDs;
- `model_version` and `prompt_version` using non-secret fixture values.

Do not include raw evidence summaries, `raw_reference`, credentials, account IDs, client order IDs, provider request payloads, or local paths.

### 5.2 Contribution frame

Derive the exact deterministic quantities in code:

- `calibrated_probability`;
- `weight = calibration_score * confidence_stake`;
- weighted contribution;
- total weight;
- disagreement;
- aggregation status;
- abstention reason.

The example must include:

1. consensus within the disagreement threshold;
2. excessive disagreement producing `abstain`;
3. incomplete juror set producing `abstain`;
4. zero total weight producing `abstain`;
5. invalid values rejected before aggregation.

### 5.3 Edge and risk frame

Use synthetic option strategy values:

- `jury_probability`;
- `net_debit`;
- `spread_width`;
- `slippage_buffer`;
- `market_hurdle`;
- `probability_edge`;
- `minimum_edge`;
- `account_equity`;
- `risk_fraction`;
- `maximum_loss`;
- `contract_cap`;
- `approved_quantity`.

Show that formulas are deterministic and that the model does not choose the maximum loss, risk fraction, contract cap, or approved quantity.

### 5.4 Decision/audit frame

Use redacted event rows:

- `event_type`;
- `occurred_at`;
- `case_label`;
- `decision`;
- `approved_quantity`;
- `maximum_loss_bucket`;
- `mode` (`recorded` or `paper`);
- `provider_status`;
- `fallback_reason`;
- `recorded_provenance`.

Do not include raw client order IDs, account numbers, broker order IDs, API responses, or precise private references. If a join is needed, use synthetic fixture IDs and explain that they are not production identifiers.

## 6. Jev/TypeSafe decision contract

RiskCourt already uses Jev/TypeSafe as a bounded provider for evidence-only juror judgments. This plan does not redefine that contract. It documents the additional typed review decisions that could protect the analysis workflow.

### 6.1 Existing provider contract to preserve

The provider must continue to:

- receive only sanitized, role-scoped state;
- answer bounded typed questions rather than generate executable instructions;
- return a probability/answer that passes strict parsing and range checks;
- identify only known evidence and known juror context;
- remain optional and unavailable-safe;
- preserve the deterministic forecast or aggregate when operating in shadow mode;
- expose provider metadata separately from evidence quality and execution authorization.

### 6.2 Optional inspection judgments

If Jev is later added to the analysis-only workflow, use:

1. **Noul — contains sensitive material**
   - true if the candidate frame includes credentials, account identifiers, order identifiers, personal data, raw provider payloads, or unrestricted references;
   - false only when the redaction checker and deterministic field allowlist pass.

2. **Choice — next review action**
   - `review_sanitization`;
   - `review_forecast_math`;
   - `review_disagreement`;
   - `review_provider_fallback`;
   - `review_paper_provenance`;
   - `no_actionable_issue`.

3. **Score — evidence completeness**
   - level 0: no usable evidence;
   - level 1: synthetic demonstration only;
   - level 2: recorded fixture replayed locally;
   - level 3: provider shadow comparison with sanitized state;
   - level 4: paper read/order lifecycle evidence independently captured;
   - level 5: full release evidence with account, execution, exit, and P&L provenance.

The score must describe evidence completeness, not trade quality or probability correctness.

### 6.3 State allowlist

Permitted semantic-review state:

- state schema version;
- juror role label;
- forecast outcome;
- bounded probability and calibration values;
- confidence stake;
- evidence type/count, not raw evidence;
- forecast horizon age/bucket;
- prompt/model version labels;
- deterministic status and fallback reason;
- synthetic case label.

Forbidden state:

- API keys and secrets;
- broker account IDs and balances;
- raw Alpaca responses;
- client/broker order IDs;
- user identity or local filesystem paths;
- raw news, quote, or market-bar payloads;
- instructions to submit, cancel, resize, or exit a trade;
- kill-switch override requests.

### 6.4 Threshold and fallback policy

- `off`: no provider request; deterministic analysis only.
- `shadow`: provider may be called with sanitized state; the deterministic analysis and decision remain primary.
- `active`: only the pre-existing bounded provider contract may affect the juror result, never the risk policy or execution permission.
- Any timeout, provider error, invalid answer, unknown evidence, stale forecast, low confidence, or policy conflict must produce a recorded fallback or abstention.
- A provider response must never turn `abstain` into an executable approval.
- Approval and execution remain explicit, idempotent, and kill-switch-aware.

## 7. Implementation phases

### Phase 0 — preserve the checkout and establish the package boundary

1. Confirm the branch is `codex/jev-detailed-repo-plans-20260925`.
2. Record `git status --short --branch`.
3. Record that `frontend/src/App.tsx` is pre-existing and outside scope.
4. Read `README.md`, `docs/FIVE_DAY_TODO.md`, `docs/DETAILED_TODO.md`, and the current TypeSafe/provider tests before editing.
5. Confirm whether the eventual examples belong under `docs/examples/` or another existing developer-only location.
6. Keep the first package documentation-only until the user approves implementation.

**Gate:** no frontend, provider, execution, database, or deployment behavior changes.

### Phase 1 — inventory contracts and execution boundaries

1. Inspect `backend/src/riskcourt/domain.py` for probability, evidence, approval, execution, and P&L contracts.
2. Inspect `backend/src/riskcourt/typesafe_state.py` for state construction, sensitive-key rejection, and role scoping.
3. Inspect `backend/src/riskcourt/typesafe_provider.py` for request/question construction, response parsing, validation, fallback, and shadow metadata.
4. Inspect `backend/src/riskcourt/typesafe_calibration.py` for recorded calibration fields and outcome linkage.
5. Inspect `backend/src/riskcourt/probability_engine.py` for complete-jury and abstention behavior.
6. Inspect `backend/src/riskcourt/strategy_math.py` for calibration, edge, hurdle, loss, and sizing formulas.
7. Inspect personal-store/audit/export code for redacted event shapes.
8. Inspect `backend/tests/test_typesafe_state.py`, `test_typesafe_provider.py`, `test_typesafe_calibration.py`, `test_probability_engine.py`, `test_risk_limits.py`, `test_personal_store.py`, and `test_personal_api.py`.
9. Build a contract table that maps each proposed visualizer column to its code owner and evidence source.

**Gate:** no visualizer column is treated as authoritative unless its producer and invariant are identified.

### Phase 2 — define the redaction and fixture boundary

1. Define a fixed allowlist for analysis fields.
2. Define a fixed denylist for keys and values containing `api`, `secret`, `credential`, `account`, `order`, `token`, or raw reference data.
3. Replace case IDs, order IDs, account IDs, and evidence IDs with stable synthetic labels.
4. Bucket or remove balances and exact P&L values unless the example explicitly needs a deterministic formula.
5. Use fixed timestamps with no user-specific timezone or machine path.
6. Mark every frame as `synthetic`, `recorded_fixture`, or `sanitized_export`.
7. Ensure the visualizer example cannot import the RiskCourt package in a way that opens a database or network connection.
8. If helper code is authorized, add tests for redaction and no-network execution.

**Gate:** the snippet can be run in a browser visualizer without exposing private or actionable trading data.

### Phase 3 — build the juror aggregation example

1. Create three synthetic juror rows for one case and horizon.
2. Compute calibrated probabilities using the same shrinkage formula as `calibrated_probability`.
3. Compute calibration/confidence weights.
4. Show weighted contributions and total weight.
5. Compute disagreement and compare it to the configured threshold.
6. Produce `ready` and `abstain` cases in separate fixture rows.
7. Demonstrate incomplete jury and zero-weight abstention.
8. Demonstrate invalid probabilities being rejected before the aggregation table is produced.
9. Compare the final visualizer result with `aggregate_forecasts` on the same synthetic values.

**Gate:** the example is explanatory only and numerically agrees with deterministic unit-test expectations.

### Phase 4 — build the edge, loss, and sizing example

1. Create a synthetic vertical spread or defined-risk strategy row.
2. Calculate option-implied hurdle from debit, width, and slippage.
3. Calculate probability edge and compare with minimum edge.
4. Calculate maximum loss using deterministic formula and fees.
5. Calculate defined-risk contract count under account/risk/cap inputs.
6. Include no-edge, invalid-width, invalid-debit, and contract-cap cases.
7. Show that no Jev field supplies a risk limit or sizing policy.
8. Label the output as a calculation trace, not a recommendation or trade instruction.

**Gate:** every calculated output is reproducible from explicit inputs and no external provider is involved.

### Phase 5 — build the provenance and fallback example

1. Create provider responses for valid, malformed, unknown-evidence, low-confidence, unavailable, stale, and shadow-disagreement cases.
2. Map each response to the provider validation result.
3. Show deterministic fallback for all invalid or unavailable cases.
4. Separate `provider_model`, `prompt_version`, `decision_source`, `calibration_score`, and `evidence_quality`.
5. Show recorded versus paper mode as distinct provenance values.
6. Show that `approval_issued` requires deterministic policy and explicit human-approved flow, not a provider label.
7. Show that `execution_updated` and P&L events are separate from forecast judgments.

**Gate:** no provider response can be mistaken for a paper-order artifact or live-performance evidence.

### Phase 6 — optional Jev review-routing integration

Only after the analysis examples and redaction tests pass:

1. Define a versioned question set for analysis review.
2. Use a narrow state object containing only allowed derived fields.
3. Inject the TypeSafe client in tests; never call the live service in unit tests.
4. Add `off`, `shadow`, and optional `active` configuration only for the review-routing surface.
5. Require strict primitive type and candidate validation.
6. Store redacted review provenance separately from forecast and execution provenance.
7. Route low-confidence or sensitive-state judgments to human review or deterministic block.
8. Add rate-limit, timeout, missing-key, provider-unavailable, malformed-response, and stale-data tests.
9. Keep the execution path unchanged when the provider is disabled or unavailable.

**Gate:** Jev is advisory for analysis and evidence triage; execution remains deterministic, explicitly approved, paper-only, and kill-switch-aware.

### Phase 7 — verification

Run local checks appropriate to the eventual files. For a documentation-only package, at minimum:

```powershell
git diff --check
```

If helper code is authorized, run the repository's existing full local gate, including backend tests, Ruff, mypy, frontend lint/typecheck/tests/build, secret scan, and recorded/browser checks as applicable. Also run targeted tests:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_typesafe_state.py backend/tests/test_typesafe_provider.py backend/tests/test_typesafe_calibration.py backend/tests/test_probability_engine.py backend/tests/test_risk_limits.py -q
```

Use a temporary recorded state directory for smoke testing. Do not submit a paper order merely to prove a visualizer example.

Evidence must be categorized:

- **Local deterministic:** unit tests, fixture replay, calculation comparison.
- **Provider:** TypeSafe API contract, model version, redacted request/response, fallback behavior.
- **Paper account:** read-only account/clock/position evidence or explicitly authorized order lifecycle evidence.
- **Hosted:** deployed endpoint and frontend/browser path.
- **Submission/publication:** separate user-authorized boundary.

### Phase 8 — handoff and release boundary

1. Review the diff for only plan/example/helper files.
2. Confirm `frontend/src/App.tsx` remains untouched.
3. Confirm no secret, account ID, order ID, raw market payload, or local absolute path entered a committed artifact.
4. Run `git status --short --branch` and `git diff --check`.
5. Do not commit, push, open a PR, merge, deploy, submit, or place a paper order without explicit authorization.
6. Hand off the first real manual gate: provider contract verification, recorded three-juror replay, or read-only paper preflight.

## 8. Verification matrix

| Area | Positive evidence | Negative evidence required | Stop condition |
|---|---|---|---|
| State redaction | allowlisted derived fields only | secret/account/order/raw-reference field | stop and remove artifact |
| Forecasts | probabilities, horizons, calibration, and evidence counts visible | stale horizon or unbounded probability accepted | abstain or reject |
| Aggregation | complete jury and weighted result match deterministic code | missing juror, zero weight, or excessive disagreement becomes approval | preserve abstention |
| Edge | hurdle and edge reproduce formula | model field changes minimum edge or sizing | preserve code-owned policy |
| Risk | maximum loss and caps remain explicit | provider output changes risk limit | fail closed |
| Approval | explicit human-bound artifact and expiry | forecast alone appears executable | block |
| Execution | recorded/paper labels and state transitions separate | recorded data presented as live performance | stop release claim |
| Kill switch | kill switch blocks risk-increasing execution | model/provider can override switch | fail closed |
| Calibration | outcomes link to sanitized forecast metadata | calibration score is treated as truth | label as historical evidence |
| Provider | valid typed response parses | timeout/malformed/unknown/stale falls back | deterministic fallback |

## 9. Risks and mitigations

### Risk: visualization introduces pandas into a safety-critical runtime

**Mitigation:** documentation/developer-only snippets, no runtime import, dependency diff check, and no data path from API/database to browser tool.

### Risk: a chart or table is mistaken for execution evidence

**Mitigation:** visible `synthetic`/`recorded`/`paper` labels, separate evidence categories, and explicit no-trading disclaimer.

### Risk: raw provider or Alpaca data leaks to a hosted service

**Mitigation:** allowlist fields, denylist sensitive keys, synthetic IDs, no upload workflow, and a pre-run redaction test.

### Risk: Jev probability or confidence overrules deterministic policy

**Mitigation:** provider can only produce a bounded forecast/juror result; risk limits, approval artifacts, kill switch, execution, and exits remain code-owned.

### Risk: provider drift is hidden by permissive parsing

**Mitigation:** versioned question set, strict typed parsing, injected transport tests, recorded response fixtures, and a separately scheduled live contract check.

### Risk: current branch work is overwritten

**Mitigation:** dedicated feature branch and explicit exclusion of `frontend/src/App.tsx`.

## 10. Completion checklist

- [ ] This plan is reviewed by the user.
- [ ] The first visualizer use case is selected.
- [ ] The final documentation/example location is agreed.
- [ ] No pandas runtime dependency is added without separate approval.
- [ ] Forecast, contribution, edge, risk, and provenance frames are sanitized.
- [ ] The juror example covers consensus, disagreement, missing juror, zero weight, and invalid values.
- [ ] The edge example covers hurdle, minimum edge, maximum loss, sizing, and invalid inputs.
- [ ] The provenance example covers provider success, shadow disagreement, malformed output, unavailable provider, stale evidence, and deterministic fallback.
- [ ] No example can submit, cancel, modify, or authorize an order.
- [ ] Recorded, paper, and hosted evidence remain visibly distinct.
- [ ] Jev/TypeSafe state is versioned, role-scoped, and free of secrets/raw references.
- [ ] `off` remains safe and deterministic.
- [ ] Unit tests cover any helper code and no-network behavior.
- [ ] The full local gate is run if implementation is authorized.
- [ ] `git diff --check` passes.
- [ ] No commit, push, PR, merge, deployment, submission, account mutation, or paper order occurs without explicit authorization.

## 11. Proposed review questions

1. Should the first RiskCourt example explain juror aggregation or audit/provenance export?
2. Should any real sanitized paper evidence be admitted, or should the first package be synthetic/recorded-only?
3. Should Jev review-routing remain entirely shadow-mode until calibration evidence is collected?
4. Which fields are acceptable for an operator-facing analysis export, and which must remain internal?
5. What independent evidence is required before any active provider or paper-mode claim is made?
