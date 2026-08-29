# Verified LabLab Event Requirements

**Event:** Alpaca AI Trading Agents Hackathon

**Checked:** August 29, 2026

**Official submission cutoff:** September 4, 2026 at 8:30 PM India Standard Time

**Internal planning constraint:** Five focused build days; submit before the official cutoff with a safety buffer.

This file is the repository's source of truth for event requirements. Recheck the event page and dashboard before final submission because LabLab reserves the right to amend the event.

## Challenge

- Track: **Options Alpha Agents**.
- Build an autonomous AI trading agent designed to generate paper-trading P&L on Alpaca.
- Demonstrate a clear, testable strategy that identifies opportunities, makes decisions, manages positions, and operates during the competition.
- Development and judging use Alpaca's paper-trading environment; no real capital is required.

## Mandatory technical requirements

- Use Alpaca's **Trading API**.
- Use at least one of Alpaca's **MCP server or CLI**.
- The strategy **must incorporate options trading**.
- The submitted system must be an **autonomous AI trading agent**, not only a research dashboard or manual order form.
- The project must be original, open source, and MIT-compatible.

## Alpaca account requirements

- Any paper account may be used during development.
- Final judging requires a **brand-new, fresh Alpaca paper account dedicated to this hackathon**.
- An existing or reused account is not eligible for judging.
- The competition account starting balance must be **$100,000**.
- The final submission must include the Alpaca paper account ID used for the hackathon so judges can inspect activity and P&L.
- Never commit or publish the API key or secret key. Supply the account ID only in the intended LabLab submission field unless organizers say otherwise.
- For the revised defined-risk spread strategy, confirm that the final account has the necessary options trading level. The preferred implementation uses multi-leg spreads and therefore expects Level 3; if unavailable, pivot to a Level-2 long-call/long-put variant rather than becoming ineligible.

User-confirmed status:

- Eligibility: confirmed.
- Team name: confirmed.
- Paper account and API keys: created.
- Still to verify: the created account is new, dedicated, starts at $100,000, and has the required options level.

## Additional required project artifact

- Provide a one-page write-up covering:
  - AI logic.
  - Risk gates.
  - Alpaca infrastructure implementation.

## Submission fields and media

### Basic information

- Project title: clear and descriptive; general LabLab guidance says maximum 50 characters.
- Short description: general guidance says maximum 255 characters.
- Long description: general guidance says minimum 100 words.
- Main track/category.
- Technology tags.

### Media

- Cover image in PNG or JPG, 16:9.
- Video presentation. General LabLab guidance says within five minutes and under 300 MB; keep the RiskCourt video to 2–3 minutes.
- Slide presentation in PDF.
- The rule book says MP4 and PDF presentation formats are mandatory; verify how the live form accepts the video because the general guide describes a video link.

### Code and demo

- Public GitHub repository.
- Demo application platform.
- Public application URL for interactive judging.
- LabLab's general rule book names Streamlit, Replit, or Vercel. If another host is used, confirm acceptance before submission.

### Competition-specific fields

- Alpaca paper trading account ID used by the submitted agent.
- Up to five public social-post links.

## Judging criteria

No percentage weights were published on the event page.

1. **P&L Performance** — paper-trading performance and effectiveness of the trading strategy.
2. **Technology Implementation** — effective use of Alpaca Trading API, MCP/CLI, and other required technology in an autonomous agent.
3. **Creativity & Originality** — originality of the strategy, agent behavior, and solution.
4. **Presentation & Execution** — clarity, live behavior, strategy reasoning, and results.
5. **Social Engagement** — relevant for the separate social component; quality and engagement may both matter.

## Social engagement challenge

- Share build progress publicly on X and/or LinkedIn.
- Posts should explain process, reasoning, experiments, setbacks, progress, or final results.
- Tag both LabLab and Alpaca.
  - X: `@lablabai` and `@AlpacaHQ`.
  - LinkedIn: `lablab.ai` and `Alpaca`.
- Submit up to five post links.
- Two winning teams each receive $500 USD plus one month of Algo Trader Plus for every team member.
- Social posting is optional for the main build, but it has a separate prize and can improve visibility.

## Prize structure

- Displayed total value: **$6,300**.
- Main prizes:
  - First: $2,500 plus $300 in Featherless credits.
  - Second: $1,500.
  - Third: $1,000.
- Social engagement: two teams receive $500 each plus the subscription benefit above.
- The event states that AlpacaDB, Inc. pays a $6,000 USD cash pool directly.
- Prizes are paid to individuals, not companies/teams. A winning team designates one payee or arranges a split with Finance in advance.
- Payment may take up to 90 days after documents clear.
- Winners must provide a government ID, bank details, and W-9 or W-8BEN as applicable. Non-US withholding and bank fees may reduce the received amount.

## General participation and conduct rules

- Teams may contain 1–6 people.
- Register on LabLab and join its Discord.
- Plagiarism, voting manipulation, cheating, system tampering, unauthorized automation, or fraudulent behavior can cause disqualification.
- Mentors/organizers may participate but cannot receive prizes; participating mentors/organizers cannot judge.
- Manual submission may be available for six hours after the deadline only for a valid reason and prior organizer/mentor approval. It is not a normal backup plan.
- Submitted content must not infringe third-party rights. LabLab's terms grant broad rights to display and promote submitted content.

## Disclosures that must shape the product and submission

- Paper trading is simulated and does not represent real trading or guarantee future results.
- The product must not present content as investment advice or a recommendation.
- Options involve substantial risk; avoid unsupported return claims.
- Report P&L as competition paper performance with timestamps and account provenance, never as expected live performance.

## Current competitive landscape

At the time of review, the live page showed 3,110 participants, 975 teams, 12 submissions, and nine submissions in the Options Alpha Agents track. This is a changing snapshot, not a final count.

Several live submissions already emphasize:

- Deterministic risk gates and abstention.
- Human approval and kill switches.
- Multi-agent adversarial debate.
- Bull-call spreads, long-gamma strategies, hedging, straddles, or volatility forecasts.
- Reproducible claims and paper-trading dashboards.

Therefore, “multiple agents debate, then a risk engine approves a spread” is not sufficiently original by itself.

## Strategic response

The revised RiskCourt differentiator is an **agent prediction market**:

- Independent AI jurors estimate outcome probabilities and stake confidence.
- A deterministic calibration layer aggregates those beliefs.
- Alpaca's option chain supplies the market-implied break-even probability proxy.
- The agent trades a defined-risk option position only when the internal probability clears the option-implied hurdle by a configured edge margin.
- The judge sees jury odds, market odds, expected edge, maximum loss, execution, and P&L in one Decision Card.

This keeps the courtroom story but makes the technical and trading mechanism substantially more specific than generic debate.

## Sources

- [Official event page](https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon)
- [Live dashboard](https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon/live)
- [LabLab Hackathon Guidelines](https://lablab.ai/ai-articles/hackathon-guidelines)
- [LabLab Hackathon Rule Book](https://lablab.ai/hackathon-rules)
- [LabLab Terms of Use — Participation Terms](https://lablab.ai/terms-of-use#16-participation-terms)
- [Alpaca options overview](https://docs.alpaca.markets/us/docs/options-trading-overview)
- [Alpaca option-chain API](https://docs.alpaca.markets/us/reference/optionchain)
- [Alpaca multi-leg options guide](https://docs.alpaca.markets/us/v1.4.2/docs/options-level-3-trading)
- [Alpaca paper trading](https://docs.alpaca.markets/us/docs/paper-trading)
