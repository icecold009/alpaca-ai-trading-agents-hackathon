# LabLab submission fields — main release draft

This is a copy-ready draft for the LabLab form. It reflects the public `main`
release and keeps only account, media, and social values unresolved. Never put
API keys, secrets, order IDs, or account IDs in this file.

## Basic information

| Field | Draft value | Check |
|---|---|---|
| Project title | **RiskCourt** | Within the 50-character guidance |
| Short description | RiskCourt is a paper-only options agent where three calibrated AI jurors debate evidence, then deterministic risk gates trade a defined-risk spread only when jury odds clear the option-implied hurdle. | Under 255 characters |
| Track/category | Options Alpha Agents | Confirm against the live form |
| Technology tags | Alpaca, Python, FastAPI, React, TypeScript, Vite, Options, OpenAI | Select only labels offered by the form |

## Long description

RiskCourt is an autonomous, paper-only options agent built as an AI prediction market. Independent jurors study market structure, catalysts, and volatility/options structure, then return evidence-bound probability forecasts and confidence stakes. A deterministic calibration layer aggregates those forecasts and compares the result with a defined-risk spread's option-payoff break-even proxy. The risk court trades only when the jury probability clears the hurdle by a configured margin and every freshness, liquidity, account, drawdown, approval, and idempotency gate passes. The MVP allows one contract and caps loss at 0.5% of account equity. Recorded mode replays twelve credential-free cases, including trade, abstain, veto, provider failure, stale data, disagreement, and prompt-injection paths. Alpaca Trading API adapters provide paper account, market-data, option-chain, order-mapping, lifecycle, and P&L boundaries. Paper performance is simulated, not live performance or investment advice; options involve substantial risk.

## Code and demo

| Field | Value |
|---|---|
| Public GitHub repository | https://github.com/icecold009/alpaca-ai-trading-agents-hackathon/tree/main | Confirm it opens while logged out |
| Demo platform | Render Static Site | Use `Other` if Render is not listed |
| Public application URL | https://riskcourt-frontend.onrender.com | Confirm it opens while logged out |
| Alpaca paper account ID | **PENDING — enter only in the intended LabLab field; never commit here** |

## Media

| Field | Local artifact / final value |
|---|---|
| Cover image | [`assets/RiskCourt-cover.png`](assets/RiskCourt-cover.png) |
| Slide presentation | [`assets/RiskCourt-submission-slides.pdf`](assets/RiskCourt-submission-slides.pdf) |
| Editable deck | [`assets/RiskCourt-submission-slides.pptx`](assets/RiskCourt-submission-slides.pptx) |
| Video presentation | **PENDING — record the 2–3 minute script from `VIDEO_RUN_OF_SHOW.md`** |

## Social engagement

Submit no more than five public links, only after confirming the post contains no secrets, account identifiers, unsupported performance claims, or private URLs.

1. **PENDING — X or LinkedIn build-progress link**
2. **PENDING — optional experiment/setback link**
3. **PENDING — optional final-demo link**

## Final verification

- Recheck title and short-description lengths against the live form.
- Replace only the `PENDING` values that have independently verified evidence.
- Confirm the public repository, hosted URL, video, and PDF are reachable while logged out.
- Enter the fresh-account ID only in LabLab and preserve the private account/order/P&L evidence separately.
- Do not submit until FD-052, FD-056, FD-059, and FD-060 are explicitly green.
