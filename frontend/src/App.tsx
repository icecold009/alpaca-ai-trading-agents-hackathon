import { useState } from "react";

import { recordedCases } from "./recordedCases";

const jurorNames: Record<string, string> = {
  juror_market: "Market structure",
  juror_catalyst: "Catalyst",
  juror_volatility: "Options structure",
};

function percent(value: string, suffix = "%") {
  return `${(Number(value) * 100).toFixed(1)}${suffix}`;
}

function money(value: string) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
  }).format(Number(value));
}

function App() {
  const [selectedCaseId, setSelectedCaseId] = useState(recordedCases[0].case_id);
  const selectedCase =
    recordedCases.find((recordedCase) => recordedCase.case_id === selectedCaseId) ??
    recordedCases[0];
  const isApproved =
    selectedCase.verdict.decision === "approve" || selectedCase.verdict.decision === "resize";
  const execution = selectedCase.executions.at(-1);
  const pnl = selectedCase.pnl_snapshots.at(-1);

  return (
    <main className="min-h-screen bg-[#050816] px-4 py-8 text-slate-100 sm:px-6 sm:py-12">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-8">
        <header className="flex flex-col gap-5 border-b border-white/10 pb-8 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-4">
            <p className="w-fit rounded-full border border-emerald-400/30 bg-emerald-400/10 px-3 py-1 text-sm font-medium text-emerald-200">
              Recorded mode · no credentials required
            </p>
            <div>
              <h1 className="text-4xl font-semibold tracking-tight text-white sm:text-6xl">
                RiskCourt
              </h1>
              <p className="mt-3 max-w-3xl text-base leading-7 text-slate-300 sm:text-lg">
                Three AI jurors price the outcome. Deterministic policy trades only when their
                calibrated odds clear the option-implied hurdle.
              </p>
            </div>
          </div>
          <div className="text-sm text-slate-400">
            <span className="block uppercase tracking-[0.18em] text-slate-400">Recorded at</span>
            <time dateTime={selectedCase.as_of}>{new Date(selectedCase.as_of).toUTCString()}</time>
          </div>
        </header>

        <nav aria-label="Recorded cases" className="grid gap-3 sm:grid-cols-2">
          {recordedCases.map((recordedCase) => {
            const selected = recordedCase.case_id === selectedCase.case_id;
            return (
              <button
                key={recordedCase.case_id}
                type="button"
                aria-pressed={selected}
                onClick={() => setSelectedCaseId(recordedCase.case_id)}
                className={`rounded-2xl border p-4 text-left transition focus-visible:outline-3 focus-visible:outline-offset-3 focus-visible:outline-cyan-300 ${
                  selected
                    ? "border-cyan-300 bg-cyan-300/10"
                    : "border-white/10 bg-white/5 hover:border-white/25"
                }`}
              >
                <span className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-300">
                  {recordedCase.verdict.decision === "veto" ? "Veto case" : "Edge-positive case"}
                </span>
                <span className="mt-2 block font-medium text-white">{recordedCase.name}</span>
              </button>
            );
          })}
        </nav>

        <section aria-labelledby="case-heading" className="space-y-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-sm uppercase tracking-[0.18em] text-slate-400">
                {selectedCase.underlying_symbol} · Recorded decision
              </p>
              <h2 id="case-heading" className="mt-1 text-2xl font-semibold text-white sm:text-3xl">
                Jury odds vs. market hurdle
              </h2>
            </div>
            <span
              className={`w-fit rounded-xl px-4 py-2 text-sm font-bold uppercase tracking-wide ${
                isApproved ? "bg-emerald-300 text-emerald-950" : "bg-rose-300 text-rose-950"
              }`}
            >
              Verdict: {selectedCase.verdict.decision}
            </span>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            {selectedCase.forecasts.map((forecast) => (
              <article
                key={forecast.forecast_id}
                className="rounded-2xl border border-white/10 bg-white/5 p-5"
              >
                <div className="flex items-start justify-between gap-3">
                  <p className="text-sm font-medium text-slate-400">
                    {jurorNames[forecast.juror_id] ?? forecast.juror_id}
                  </p>
                  <span className="rounded-full border border-white/10 bg-white/5 px-2 py-1 text-[0.65rem] font-semibold uppercase tracking-wide text-slate-400">
                    {forecast.evidence_ids.length} evidence refs
                  </span>
                </div>
                <p className="mt-3 text-4xl font-semibold text-white">
                  {percent(forecast.probability)}
                </p>
                <dl className="mt-3 grid grid-cols-2 gap-3 text-xs">
                  <div>
                    <dt className="uppercase tracking-wide text-slate-500">Confidence stake</dt>
                    <dd className="mt-1 text-sm font-semibold text-cyan-200">
                      {percent(forecast.confidence_stake)}
                    </dd>
                  </div>
                  <div>
                    <dt className="uppercase tracking-wide text-slate-500">Calibration</dt>
                    <dd className="mt-1 text-sm font-semibold text-cyan-200">
                      {percent(forecast.calibration_score)}
                    </dd>
                  </div>
                </dl>
                <p className="mt-4 text-sm leading-6 text-slate-400">{forecast.rationale}</p>
              </article>
            ))}
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            <Metric
              label="Calibrated jury odds"
              value={percent(selectedCase.strategy.jury_probability)}
            />
            <Metric
              label="Option-implied hurdle"
              value={percent(selectedCase.strategy.market_hurdle)}
            />
            <Metric
              label="Probability edge margin"
              value={`${Number(selectedCase.strategy.probability_edge) >= 0 ? "+" : ""}${percent(
                selectedCase.strategy.probability_edge,
                " pp",
              )}`}
              accent={isApproved ? "positive" : "negative"}
            />
          </div>
          <p className="mt-4 text-sm text-slate-400">
            Minimum edge required:{" "}
            <span className="font-semibold text-slate-200">
              {percent(selectedCase.strategy.minimum_edge, " pp")}
            </span>
            . The verdict is deterministic and evidence-bound.
          </p>
        </section>

        <div className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
          <section
            aria-labelledby="position-heading"
            className="rounded-3xl border border-white/10 bg-white/5 p-6"
          >
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-sm uppercase tracking-[0.18em] text-cyan-300">Defined risk</p>
                <h2 id="position-heading" className="mt-2 text-2xl font-semibold text-white">
                  Selected option legs
                </h2>
              </div>
              <div className="text-right">
                <p className="text-xs uppercase tracking-wide text-slate-400">Maximum loss</p>
                <p className="mt-1 text-xl font-semibold text-white">
                  {money(
                    isApproved && selectedCase.approval
                      ? selectedCase.approval.maximum_loss
                      : selectedCase.intent.maximum_loss,
                  )}
                </p>
              </div>
            </div>
            <ul className="mt-6 space-y-3">
              {selectedCase.intent.legs.map((leg) => (
                <li
                  key={leg.occ_symbol}
                  className="flex flex-col gap-2 rounded-2xl border border-white/10 bg-slate-950/50 p-4 sm:flex-row sm:items-center sm:justify-between"
                >
                  <code className="text-sm text-slate-200">{leg.occ_symbol}</code>
                  <span className="text-sm font-medium uppercase text-cyan-200">
                    {leg.position_intent.replaceAll("_", " ")} · requested {leg.quantity}
                  </span>
                </li>
              ))}
            </ul>
            <p className="mt-5 text-sm text-slate-400">
              Net debit {money(selectedCase.strategy.net_debit)} per share · width{" "}
              {money(selectedCase.strategy.spread_width)} · {selectedCase.intent.direction} intent
            </p>
          </section>

          <section
            aria-labelledby="record-heading"
            className={`rounded-3xl border p-6 ${
              isApproved
                ? "border-emerald-400/20 bg-emerald-400/5"
                : "border-rose-400/20 bg-rose-400/5"
            }`}
          >
            <p
              className={`text-sm uppercase tracking-[0.18em] ${
                isApproved ? "text-emerald-300" : "text-rose-300"
              }`}
            >
              Decision record
            </p>
            <h2 id="record-heading" className="mt-2 text-2xl font-semibold text-white">
              {isApproved ? "Approved after deterministic resize" : "Trade vetoed — no order sent"}
            </h2>
            <p className="mt-4 leading-7 text-slate-300">{selectedCase.verdict.reasons[0]}</p>

            {isApproved && execution && pnl ? (
              <dl className="mt-6 grid grid-cols-2 gap-4 border-t border-white/10 pt-5 text-sm">
                <RecordValue
                  label="Approved quantity"
                  value={`${selectedCase.verdict.approved_quantity} contract`}
                />
                <RecordValue label="Order status" value={execution.status} />
                <RecordValue label="Client order ID" value={execution.client_order_id} mono />
                <RecordValue
                  label="Paper P&L"
                  value={`${Number(pnl.unrealized_pnl) >= 0 ? "+" : ""}${money(pnl.unrealized_pnl)}`}
                  positive
                />
              </dl>
            ) : (
              <div className="mt-6 rounded-2xl border border-rose-300/20 bg-slate-950/40 p-4 text-sm text-rose-100">
                No approval artifact, Alpaca order, execution record, or P&amp;L follows this veto.
              </div>
            )}
          </section>
        </div>

        <footer className="border-t border-white/10 pt-6 text-sm leading-6 text-slate-400">
          Paper trading is simulated and does not guarantee future results. This project does not
          provide investment advice.
        </footer>
      </div>
    </main>
  );
}

function Metric({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: "positive" | "negative";
}) {
  const color =
    accent === "positive"
      ? "text-emerald-300"
      : accent === "negative"
        ? "text-rose-300"
        : "text-white";
  return (
    <div className="rounded-2xl border border-white/10 bg-slate-900/70 p-5">
      <p className="text-sm text-slate-400">{label}</p>
      <p className={`mt-2 text-3xl font-semibold ${color}`}>{value}</p>
    </div>
  );
}

function RecordValue({
  label,
  value,
  mono = false,
  positive = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
  positive?: boolean;
}) {
  return (
    <div className="min-w-0">
      <dt className="text-slate-400">{label}</dt>
      <dd
        className={`mt-1 break-words font-medium capitalize ${mono ? "font-mono text-xs" : ""} ${
          positive ? "text-emerald-300" : "text-slate-100"
        }`}
      >
        {value}
      </dd>
    </div>
  );
}

export default App;
