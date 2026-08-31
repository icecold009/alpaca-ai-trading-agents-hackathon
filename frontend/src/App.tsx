import { useEffect, useState } from "react";

import { recordedCases } from "./recordedCases";
import { loadRecordedCases } from "./runtime";

const jurorNames: Record<string, string> = {
  juror_market: "Market structure",
  juror_catalyst: "Catalyst",
  juror_volatility: "Options structure",
};

type ReplayState =
  | "recorded"
  | "market-closed"
  | "missing-quote"
  | "provider-failure"
  | "alpaca-rejection"
  | "kill-switch";

const replayStates: Record<
  ReplayState,
  { label: string; status: string; detail: string; tone: "safe" | "blocked" | "error" }
> = {
  recorded: {
    label: "Recorded replay",
    status: "Recorded fixture ready",
    detail: "No credentials or network are required for this path.",
    tone: "safe",
  },
  "market-closed": {
    label: "Market closed",
    status: "Market closed — no order sent",
    detail: "Fresh quotes are required before a paper order can be considered.",
    tone: "blocked",
  },
  "missing-quote": {
    label: "Missing quote",
    status: "Quote unavailable — abstain",
    detail: "The candidate cannot be reconstructed without a current option quote.",
    tone: "blocked",
  },
  "provider-failure": {
    label: "Provider failure",
    status: "Provider unavailable — abstain",
    detail: "A timeout or malformed response never reaches the execution boundary.",
    tone: "error",
  },
  "alpaca-rejection": {
    label: "Alpaca rejection",
    status: "Alpaca rejected — execution stopped",
    detail: "The lifecycle records the rejection and prevents a retry from creating a duplicate.",
    tone: "error",
  },
  "kill-switch": {
    label: "Kill switch",
    status: "Kill switch active — execution disabled",
    detail: "The safety control blocks new orders while recorded replay remains available.",
    tone: "blocked",
  },
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
  const [cases, setCases] = useState(recordedCases);
  const [selectedCaseId, setSelectedCaseId] = useState(recordedCases[0].case_id);
  const [replayState, setReplayState] = useState<ReplayState>("recorded");
  const [runtimeSource, setRuntimeSource] = useState<"fixture" | "api">("fixture");
  useEffect(() => {
    if (import.meta.env.MODE === "test") return;
    let active = true;
    void loadRecordedCases().then((remoteCases) => {
      if (!active || !remoteCases?.length) return;
      setRuntimeSource("api");
      setCases(remoteCases);
      setSelectedCaseId(remoteCases[0].case_id);
    });
    return () => {
      active = false;
    };
  }, []);
  const selectedCase =
    cases.find((recordedCase) => recordedCase.case_id === selectedCaseId) ?? cases[0];
  const isApproved =
    selectedCase.verdict.decision === "approve" || selectedCase.verdict.decision === "resize";
  const execution = selectedCase.executions.at(-1);
  const pnl = selectedCase.pnl_snapshots.at(-1);

  return (
    <main className="min-h-screen bg-[#050816] px-4 py-8 text-slate-100 sm:px-6 sm:py-12">
      <a
        href="#case-heading"
        className="sr-only z-50 rounded-lg bg-cyan-300 px-4 py-2 font-semibold text-slate-950 focus:not-sr-only focus:fixed focus:left-4 focus:top-4"
      >
        Skip to decision
      </a>
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-8">
        <header className="flex flex-col gap-5 border-b border-white/10 pb-8 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-4">
            <p className="flex w-fit items-center gap-2 rounded-full border border-emerald-400/30 bg-emerald-400/10 px-3 py-1 text-sm font-medium text-emerald-200">
              <span className="h-2 w-2 rounded-full bg-emerald-300" aria-hidden="true" />
              {runtimeSource === "api"
                ? "Recorded API · read-only"
                : "Recorded mode · no credentials required"}
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
            <span className="mt-2 block text-xs text-slate-300">
              {runtimeSource === "api"
                ? "Source: hosted recorded-case API"
                : "Source: bundled fixture"}
            </span>
          </div>
        </header>

        <nav aria-label="Recorded cases" className="grid gap-3 sm:grid-cols-2">
          {cases.map((recordedCase) => {
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

        <section
          aria-labelledby="replay-state-heading"
          className="rounded-3xl border border-white/10 bg-slate-900/70 p-5"
        >
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="text-sm uppercase tracking-[0.18em] text-cyan-300">Safety replay</p>
              <h2 id="replay-state-heading" className="mt-1 text-xl font-semibold text-white">
                Exercise failure and market states
              </h2>
            </div>
            <p className="text-sm text-slate-400">All states are dry-run UI fallbacks.</p>
          </div>
          <div aria-label="Replay states" className="mt-4 grid gap-2 sm:grid-cols-3 lg:grid-cols-6">
            {(Object.keys(replayStates) as ReplayState[]).map((state) => {
              const selected = state === replayState;
              return (
                <button
                  key={state}
                  type="button"
                  aria-pressed={selected}
                  onClick={() => setReplayState(state)}
                  className={
                    "rounded-xl border px-3 py-2 text-left text-xs font-semibold transition " +
                    "focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-cyan-300 " +
                    (selected
                      ? "border-cyan-300 bg-cyan-300/10 text-cyan-100"
                      : "border-white/10 bg-white/5 text-slate-300 hover:border-white/25")
                  }
                >
                  {replayStates[state].label}
                </button>
              );
            })}
          </div>
          <div
            role="status"
            aria-live="polite"
            className={
              "mt-4 rounded-2xl border p-4 " +
              (replayStates[replayState].tone === "safe"
                ? "border-emerald-400/20 bg-emerald-400/5 text-emerald-100"
                : replayStates[replayState].tone === "blocked"
                  ? "border-amber-300/20 bg-amber-300/5 text-amber-100"
                  : "border-rose-300/20 bg-rose-300/5 text-rose-100")
            }
          >
            <p className="font-semibold">{replayStates[replayState].status}</p>
            <p className="mt-1 text-sm opacity-80">{replayStates[replayState].detail}</p>
          </div>
        </section>

        <section aria-labelledby="case-heading" className="space-y-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-sm uppercase tracking-[0.18em] text-slate-400">
                {selectedCase.underlying_symbol} · Recorded decision
              </p>
              <h2
                id="case-heading"
                tabIndex={-1}
                className="mt-1 text-2xl font-semibold text-white outline-none sm:text-3xl"
              >
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
                    <dt className="uppercase tracking-wide text-slate-400">Confidence stake</dt>
                    <dd className="mt-1 text-sm font-semibold text-cyan-200">
                      {percent(forecast.confidence_stake)}
                    </dd>
                  </div>
                  <div>
                    <dt className="uppercase tracking-wide text-slate-400">Calibration</dt>
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
          <OddsComparison
            juryProbability={selectedCase.strategy.jury_probability}
            hurdle={selectedCase.strategy.market_hurdle}
          />
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
                <RecordValue label="Paper order reference" value="Private reference redacted" />
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

function OddsComparison({ juryProbability, hurdle }: { juryProbability: string; hurdle: string }) {
  const jury = Math.max(0, Math.min(1, Number(juryProbability)));
  const market = Math.max(0, Math.min(1, Number(hurdle)));
  return (
    <div
      className="rounded-2xl border border-cyan-300/15 bg-slate-950/50 p-4"
      role="img"
      aria-label={`Calibrated jury odds ${percent(juryProbability)} versus option-implied hurdle ${percent(hurdle)}`}
    >
      <div className="flex items-center justify-between gap-4 text-xs uppercase tracking-[0.16em] text-slate-400">
        <span>Decision threshold</span>
        <span className="text-cyan-200">Jury clears hurdle</span>
      </div>
      <div className="relative mt-4 h-3 rounded-full bg-white/10">
        <div
          className="absolute inset-y-0 left-0 rounded-full bg-cyan-300/80"
          style={{ width: `${jury * 100}%` }}
        />
        <div
          className="absolute -top-1 h-5 w-0.5 bg-amber-200 shadow-[0_0_12px_rgba(253,230,138,0.7)]"
          style={{ left: `calc(${market * 100}% - 1px)` }}
        />
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-slate-400">
        <span className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-cyan-300" aria-hidden="true" />
          Jury {percent(juryProbability)}
        </span>
        <span className="flex items-center gap-2">
          <span className="h-3 w-0.5 bg-amber-200" aria-hidden="true" />
          Hurdle {percent(hurdle)}
        </span>
      </div>
    </div>
  );
}

export default App;
