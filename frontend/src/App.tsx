import { useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { recordedCases } from "./recordedCases";
import {
  type AccountSummary,
  type JournalEntry,
  type PersonalDecision,
  type Portfolio,
  personalApi,
} from "./personalApi";

type View = "overview" | "opportunities" | "portfolio" | "journal" | "settings";
type ReplayState =
  | "recorded"
  | "market-closed"
  | "missing-quote"
  | "provider-failure"
  | "alpaca-rejection"
  | "kill-switch";

const jurorNames: Record<string, string> = {
  juror_market: "Market structure",
  juror_catalyst: "Catalyst",
  juror_volatility: "Options structure",
};

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

const fallbackAccount: AccountSummary = {
  mode: "recorded",
  paper: true,
  status: "recorded",
  equity: null,
  buying_power: null,
  market_open: false,
  position_count: 0,
  pending_order_count: 0,
  message: "Recorded mode is active; no broker credentials are used.",
};

function fallbackDecisions(): PersonalDecision[] {
  return recordedCases.map((payload, index) => ({
    decision_id: `local_${payload.case_id}`,
    scan_id: "local-recorded-scan",
    case_id: payload.case_id,
    mode: "recorded",
    symbol: payload.underlying_symbol,
    verdict: payload.verdict.decision,
    status: "ready",
    as_of: payload.as_of,
    freshness_until: payload.as_of,
    maximum_loss: payload.verdict.maximum_loss,
    created_at: new Date(Date.now() - index * 60_000).toISOString(),
    payload,
  }));
}

function percent(value: string | number | null | undefined, suffix = "%") {
  return `${(Number(value ?? 0) * 100).toFixed(1)}${suffix}`;
}

function money(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
  }).format(Number(value));
}

function shortTime(value: string | undefined) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit" }).format(
    new Date(value),
  );
}

function App() {
  const [view, setView] = useState<View>("overview");
  const [decisions, setDecisions] = useState<PersonalDecision[]>(fallbackDecisions);
  const [selectedDecisionId, setSelectedDecisionId] = useState(decisions[0]?.decision_id ?? "");
  const [account, setAccount] = useState<AccountSummary>(fallbackAccount);
  const [portfolio, setPortfolio] = useState<Portfolio>({
    account: fallbackAccount,
    positions: [],
    orders: [],
    kill_switch: { enabled: false, reason: "", updated_at: "" },
  });
  const [journal, setJournal] = useState<JournalEntry[]>([]);
  const [watchlist, setWatchlist] = useState<string[]>(["SPY", "QQQ"]);
  const [replayState, setReplayState] = useState<ReplayState>("recorded");
  const [runtimeSource, setRuntimeSource] = useState<"fixture" | "api">("fixture");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("Ready for a manual scan.");
  const [approval, setApproval] = useState<{
    approval_id: string;
    expires_at: string;
    quantity: number;
    maximum_loss: string;
  } | null>(null);

  const selectedDecision =
    decisions.find((item) => item.decision_id === selectedDecisionId) ?? decisions[0];
  const selectedCase = selectedDecision?.payload;
  const mode = account.mode;
  const isKillSwitchEnabled = portfolio.kill_switch.enabled;

  useEffect(() => {
    if (import.meta.env.MODE === "test") return;
    let active = true;
    void Promise.allSettled([
      personalApi.account(),
      personalApi.portfolio(),
      personalApi.watchlist(),
      personalApi.decisions(),
      personalApi.journal(),
    ]).then((results) => {
      if (!active) return;
      const [accountResult, portfolioResult, watchlistResult, decisionsResult, journalResult] =
        results;
      if (accountResult.status === "fulfilled") setAccount(accountResult.value);
      if (portfolioResult.status === "fulfilled") setPortfolio(portfolioResult.value);
      if (watchlistResult.status === "fulfilled")
        setWatchlist(watchlistResult.value.symbols.map((item) => item.symbol));
      if (decisionsResult.status === "fulfilled" && decisionsResult.value.decisions.length) {
        setRuntimeSource("api");
        setDecisions(decisionsResult.value.decisions);
        setSelectedDecisionId(decisionsResult.value.decisions[0].decision_id);
      }
      if (journalResult.status === "fulfilled") setJournal(journalResult.value.entries);
    });
    return () => {
      active = false;
    };
  }, []);

  const chartData = useMemo(
    () =>
      decisions
        .slice(0, 8)
        .reverse()
        .map((decision, index) => ({
          name: `${decision.symbol} ${index + 1}`,
          pnl: Number(decision.payload?.pnl_snapshots?.at(-1)?.unrealized_pnl ?? 0),
        })),
    [decisions],
  );

  async function scanNow() {
    setBusy(true);
    setNotice("Scanning the configured watchlist…");
    try {
      const result = await personalApi.scan(watchlist);
      if (result.decisions.length) {
        setRuntimeSource("api");
        setDecisions(result.decisions);
        setSelectedDecisionId(result.decisions[0].decision_id);
        setView("opportunities");
      }
      setNotice(
        result.failures.length
          ? `Scan completed with ${result.failures.length} safe abstention(s).`
          : "Scan completed. Review the newest opportunity.",
      );
    } catch {
      setNotice("Backend unavailable; showing the credential-free recorded workspace.");
      setView("opportunities");
    } finally {
      setBusy(false);
    }
  }

  async function vetoSelected() {
    if (!selectedDecision) return;
    setBusy(true);
    try {
      await personalApi.veto(selectedDecision.decision_id);
    } catch {
      /* local fallback */
    }
    setDecisions((items) =>
      items.map((item) =>
        item.decision_id === selectedDecision.decision_id
          ? { ...item, status: "vetoed", verdict: "veto" }
          : item,
      ),
    );
    setApproval(null);
    setNotice("Decision vetoed. No order can follow this record.");
    setBusy(false);
  }

  async function approveSelected() {
    if (!selectedDecision) return;
    setBusy(true);
    try {
      const result = await personalApi.approve(selectedDecision.decision_id);
      setApproval(result.approval);
      setNotice("Approval prepared. Review every order field before submitting.");
    } catch {
      if (
        selectedCase?.verdict?.decision === "approve" ||
        selectedCase?.verdict?.decision === "resize"
      ) {
        const localApproval = {
          approval_id: `local_approval_${selectedDecision.case_id}`,
          expires_at: new Date(Date.now() + 300_000).toISOString(),
          quantity: selectedCase.verdict.approved_quantity,
          maximum_loss: selectedCase.verdict.maximum_loss,
        };
        setApproval(localApproval);
        setNotice("Local approval preview prepared. Recorded mode cannot submit a broker order.");
      } else setNotice("This decision is not eligible for approval.");
    } finally {
      setBusy(false);
    }
  }

  async function submitSelected() {
    if (!approval) return;
    if (mode === "recorded") {
      setNotice("Recorded mode is read-only. Switch to paper mode to submit an Alpaca order.");
      return;
    }
    setBusy(true);
    try {
      const result = await personalApi.submit(
        approval.approval_id,
        `riskcourt_${selectedDecision?.case_id ?? "order"}_${Date.now()}`,
      );
      setNotice(
        result.replayed
          ? "Existing paper submission loaded safely."
          : "Paper order submitted and recorded.",
      );
      setApproval(null);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Paper submission was rejected safely.");
    } finally {
      setBusy(false);
    }
  }

  async function toggleWatchlist(symbol: string) {
    const next = watchlist.includes(symbol)
      ? watchlist.filter((item) => item !== symbol)
      : [...watchlist, symbol];
    if (!next.length) return;
    setWatchlist(next);
    try {
      await personalApi.saveWatchlist(next);
    } catch {
      setNotice("Watchlist saved locally; backend is unavailable.");
    }
  }

  async function toggleKillSwitch() {
    const enabled = !isKillSwitchEnabled;
    try {
      const result = await personalApi.killSwitch(
        enabled,
        enabled ? "Manual operator pause" : "Manual operator resume",
      );
      setPortfolio((current) => ({ ...current, kill_switch: result.kill_switch }));
    } catch {
      setPortfolio((current) => ({
        ...current,
        kill_switch: {
          ...current.kill_switch,
          enabled,
          reason: enabled ? "Manual operator pause" : "",
        },
      }));
    }
    setNotice(
      enabled
        ? "Kill switch enabled. New entries are blocked."
        : "Kill switch disabled. Review the next decision before submitting.",
    );
  }

  async function addJournalEntry(body: string) {
    if (!body.trim()) return;
    try {
      const result = await personalApi.journalEntry(body, selectedDecision?.decision_id);
      setJournal((items) => [result.entry, ...items]);
    } catch {
      const timestamp = new Date().toISOString();
      setJournal((items) => [
        {
          entry_id: `local_${Date.now()}`,
          decision_id: selectedDecision?.decision_id ?? null,
          body: body.trim(),
          created_at: timestamp,
          updated_at: timestamp,
        },
        ...items,
      ]);
    }
    setNotice("Journal entry saved.");
  }

  function openDecision(decisionId: string) {
    setSelectedDecisionId(decisionId);
    setView("opportunities");
    setApproval(null);
  }

  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link">
        Skip to workspace
      </a>
      <aside className="sidebar">
        <div className="brand-lockup">
          <div className="brand-mark">RC</div>
          <div>
            <p className="eyebrow">Personal workstation</p>
            <h1>RiskCourt</h1>
          </div>
        </div>
        <div className={`mode-card ${mode}`}>
          <span className="status-dot" />{" "}
          <span>{mode === "recorded" ? "Recorded mode" : "Paper mode"}</span>
          <small>{mode === "recorded" ? "No credentials required" : "Alpaca paper only"}</small>
        </div>
        <nav className="primary-nav" aria-label="Primary navigation">
          <NavButton active={view === "overview"} onClick={() => setView("overview")} icon="⌂">
            Overview
          </NavButton>
          <NavButton
            active={view === "opportunities"}
            onClick={() => setView("opportunities")}
            icon="◈"
          >
            Opportunities <span className="nav-count">{decisions.length}</span>
          </NavButton>
          <NavButton active={view === "portfolio"} onClick={() => setView("portfolio")} icon="◒">
            Portfolio
          </NavButton>
          <NavButton active={view === "journal"} onClick={() => setView("journal")} icon="✎">
            Journal
          </NavButton>
          <NavButton active={view === "settings"} onClick={() => setView("settings")} icon="⚙">
            Settings
          </NavButton>
        </nav>
        <div className="sidebar-footer">
          <p>Paper trading is simulated and does not guarantee future results.</p>
          <span>v0.2 · local-first</span>
        </div>
      </aside>
      <main id="main-content" className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">{viewLabel(view)}</p>
            <h2>{viewTitle(view)}</h2>
          </div>
          <div className="topbar-actions">
            <span className="source-pill">
              {runtimeSource === "api" ? "Local API connected" : "Fixture fallback"}
            </span>
            <button
              className="button button-primary"
              type="button"
              onClick={() => void scanNow()}
              disabled={busy}
            >
              {busy ? "Scanning…" : "Scan now"}
            </button>
          </div>
        </header>
        <div className="notice-bar" role="status">
          <span className="notice-icon">i</span>
          <span>{notice}</span>
          <button
            type="button"
            className="icon-button"
            aria-label="Dismiss notice"
            onClick={() => setNotice("")}
          >
            ×
          </button>
        </div>
        {view === "overview" && (
          <OverviewView
            account={account}
            portfolio={portfolio}
            decisions={decisions}
            chartData={chartData}
            onOpenDecision={openDecision}
            onToggleKillSwitch={() => void toggleKillSwitch()}
          />
        )}
        {view === "opportunities" && (
          <OpportunitiesView
            decisions={decisions}
            selectedDecision={selectedDecision}
            replayState={replayState}
            setReplayState={setReplayState}
            onOpenDecision={openDecision}
            onApprove={() => void approveSelected()}
            onVeto={() => void vetoSelected()}
            approval={approval}
            onSubmit={() => void submitSelected()}
            busy={busy}
            mode={mode}
          />
        )}
        {view === "portfolio" && (
          <PortfolioView portfolio={portfolio} chartData={chartData} decisions={decisions} />
        )}
        {view === "journal" && (
          <JournalView
            journal={journal}
            selectedDecision={selectedDecision}
            onAdd={addJournalEntry}
          />
        )}
        {view === "settings" && (
          <SettingsView
            watchlist={watchlist}
            onToggle={toggleWatchlist}
            killSwitch={isKillSwitchEnabled}
            onToggleKillSwitch={() => void toggleKillSwitch()}
          />
        )}
      </main>
    </div>
  );
}

function viewLabel(view: View) {
  return {
    overview: "Command center",
    opportunities: "Decision pipeline",
    portfolio: "Exposure & P&L",
    journal: "Private research log",
    settings: "Guardrails",
  }[view];
}
function viewTitle(view: View) {
  return {
    overview: "Good morning, operator.",
    opportunities: "Find the next defensible setup.",
    portfolio: "Know what is open.",
    journal: "Keep the reasoning close.",
    settings: "Tune the workstation safely.",
  }[view];
}

function NavButton({
  active,
  onClick,
  icon,
  children,
}: {
  active: boolean;
  onClick: () => void;
  icon: string;
  children: React.ReactNode;
}) {
  return (
    <button className={`nav-button ${active ? "active" : ""}`} type="button" onClick={onClick}>
      <span className="nav-icon" aria-hidden="true">
        {icon}
      </span>
      <span>{children}</span>
    </button>
  );
}

function OverviewView({
  account,
  portfolio,
  decisions,
  chartData,
  onOpenDecision,
  onToggleKillSwitch,
}: {
  account: AccountSummary;
  portfolio: Portfolio;
  decisions: PersonalDecision[];
  chartData: Array<{ name: string; pnl: number }>;
  onOpenDecision: (id: string) => void;
  onToggleKillSwitch: () => void;
}) {
  const latest = decisions[0];
  return (
    <div className="view-stack">
      <section className="hero-grid">
        <div className="hero-card panel-gradient">
          <div>
            <span className="eyebrow accent">Decision cockpit</span>
            <h3>
              Trade less. <em>Know why.</em>
            </h3>
            <p>
              Three independent jurors form a probability market. Deterministic policy decides when
              the edge is worth the risk.
            </p>
            <button
              className="text-button"
              type="button"
              onClick={() => onOpenDecision(latest?.decision_id ?? "")}
            >
              Open latest decision <span>→</span>
            </button>
          </div>
          <div className="hero-orbit" aria-hidden="true">
            <span />
            <span />
            <span />
          </div>
        </div>
        <div className="panel account-card">
          <PanelHeader
            eyebrow="Paper account"
            title="Account posture"
            action={
              <span className="live-indicator">
                <span className="status-dot" />
                {account.status}
              </span>
            }
          />
          <div className="account-value">
            {account.equity ? money(account.equity) : "—"}
            <small>{account.equity ? "equity" : "equity hidden in recorded mode"}</small>
          </div>
          <div className="account-grid">
            <Metric
              label="Buying power"
              value={account.buying_power ? money(account.buying_power) : "—"}
            />
            <Metric label="Open positions" value={String(account.position_count)} />
            <Metric label="Market" value={account.market_open ? "Open" : "Closed"} />
          </div>
        </div>
      </section>
      <section className="metric-grid">
        <MetricCard label="Watchlist" value="SPY · QQQ" detail="2 symbols monitored" tone="cyan" />
        <MetricCard
          label="Decisions today"
          value={String(decisions.length)}
          detail="Recorded + paper scans"
          tone="violet"
        />
        <MetricCard
          label="Current risk"
          value={portfolio.positions.length ? money(portfolio.positions[0].cost_basis) : "$0.00"}
          detail="Defined-risk only"
          tone="amber"
        />
        <MetricCard
          label="System state"
          value={portfolio.kill_switch.enabled ? "Paused" : "Armed"}
          detail={portfolio.kill_switch.enabled ? "Entries blocked" : "Approval required"}
          tone={portfolio.kill_switch.enabled ? "rose" : "green"}
        />
      </section>
      <section className="content-grid">
        <div className="panel chart-panel">
          <PanelHeader
            eyebrow="Personal performance"
            title="Decision P&L"
            action={<span className="muted-label">Last 8 decisions</span>}
          />
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="pnlFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#7dd3fc" stopOpacity={0.32} />
                    <stop offset="100%" stopColor="#7dd3fc" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#ffffff12" vertical={false} />
                <XAxis dataKey="name" hide />
                <YAxis hide domain={["auto", "auto"]} />
                <Tooltip
                  contentStyle={{
                    background: "#111827",
                    border: "1px solid #ffffff1c",
                    borderRadius: 12,
                    color: "#f8fafc",
                  }}
                  formatter={(value) => [money(String(value)), "P&L"]}
                />
                <Area
                  type="monotone"
                  dataKey="pnl"
                  stroke="#7dd3fc"
                  strokeWidth={2}
                  fill="url(#pnlFill)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <div className="chart-footer">
            <span>
              <i className="legend-dot cyan" />
              Observed paper P&L
            </span>
            <span className="muted-label">Recorded fixtures are clearly labeled</span>
          </div>
        </div>
        <div className="panel latest-panel">
          <PanelHeader
            eyebrow="Latest opportunity"
            title={latest?.symbol ?? "No scan yet"}
            action={latest ? <StatusBadge verdict={latest.verdict} /> : null}
          />
          {latest ? (
            <button
              className="decision-preview"
              type="button"
              onClick={() => onOpenDecision(latest.decision_id)}
            >
              <div className="decision-preview-top">
                <span>{latest.payload.name}</span>
                <span>{shortTime(latest.as_of)}</span>
              </div>
              <div className="edge-display">
                <strong>{percent(latest.payload.strategy.jury_probability)}</strong>
                <span>jury odds</span>
                <div className="edge-arrow">→</div>
                <strong>{percent(latest.payload.strategy.market_hurdle)}</strong>
                <span>hurdle</span>
              </div>
              <p>{latest.payload.verdict.reasons[0]}</p>
              <span className="text-button">
                Review decision <span>→</span>
              </span>
            </button>
          ) : (
            <EmptyState
              title="Run your first scan"
              detail="The default recorded workspace is ready for a credential-free rehearsal."
            />
          )}
        </div>
      </section>
      <section className="panel safety-strip">
        <div>
          <span className="eyebrow">Operator control</span>
          <h3>
            {portfolio.kill_switch.enabled
              ? "New entries are paused."
              : "The court is armed, not automatic."}
          </h3>
          <p>
            {portfolio.kill_switch.enabled
              ? "Risk-reducing exits remain available. Review the reason before resuming."
              : "Every paper order requires a fresh snapshot and an explicit confirmation."}
          </p>
        </div>
        <button
          className={`button ${portfolio.kill_switch.enabled ? "button-primary" : "button-ghost"}`}
          type="button"
          onClick={onToggleKillSwitch}
        >
          {portfolio.kill_switch.enabled ? "Resume entries" : "Enable kill switch"}
        </button>
      </section>
    </div>
  );
}

function OpportunitiesView({
  decisions,
  selectedDecision,
  replayState,
  setReplayState,
  onOpenDecision,
  onApprove,
  onVeto,
  approval,
  onSubmit,
  busy,
  mode,
}: {
  decisions: PersonalDecision[];
  selectedDecision?: PersonalDecision;
  replayState: ReplayState;
  setReplayState: (state: ReplayState) => void;
  onOpenDecision: (id: string) => void;
  onApprove: () => void;
  onVeto: () => void;
  approval: {
    approval_id: string;
    expires_at: string;
    quantity: number;
    maximum_loss: string;
  } | null;
  onSubmit: () => void;
  busy: boolean;
  mode: "recorded" | "paper";
}) {
  const selectedCase = selectedDecision?.payload;
  const isApproved =
    selectedCase?.verdict?.decision === "approve" || selectedCase?.verdict?.decision === "resize";
  return (
    <div className="view-stack">
      <section className="panel replay-panel">
        <div className="section-heading">
          <div>
            <span className="eyebrow accent">Safety replay</span>
            <h3>Exercise failure and market states</h3>
          </div>
          <span className="muted-label">All states are dry-run UI fallbacks.</span>
        </div>
        <div className="replay-buttons">
          {(Object.keys(replayStates) as ReplayState[]).map((state) => (
            <button
              key={state}
              className={`replay-button ${state === replayState ? "selected" : ""}`}
              type="button"
              aria-pressed={state === replayState}
              onClick={() => setReplayState(state)}
            >
              {replayStates[state].label}
            </button>
          ))}
        </div>
        <div className={`replay-status ${replayStates[replayState].tone}`} role="status">
          <strong>{replayStates[replayState].status}</strong>
          <span>{replayStates[replayState].detail}</span>
        </div>
      </section>
      <section className="opportunity-layout">
        <div className="panel opportunity-list">
          <PanelHeader
            eyebrow="Watchlist scan"
            title="Candidate queue"
            action={<span className="muted-label">{decisions.length} records</span>}
          />
          <div className="table-head">
            <span>Setup</span>
            <span>Edge</span>
            <span>Risk</span>
            <span>Status</span>
          </div>
          {decisions.map((decision) => (
            <button
              key={decision.decision_id}
              type="button"
              className={`opportunity-row ${decision.decision_id === selectedDecision?.decision_id ? "selected" : ""}`}
              onClick={() => onOpenDecision(decision.decision_id)}
            >
              <span>
                <strong>{decision.symbol}</strong>
                <small>{decision.payload.name}</small>
              </span>
              <span>
                <strong
                  className={
                    Number(decision.payload.strategy.probability_edge) >= 0
                      ? "positive"
                      : "negative"
                  }
                >
                  {percent(decision.payload.strategy.probability_edge, " pp")}
                </strong>
                <small>{percent(decision.payload.strategy.jury_probability)} jury</small>
              </span>
              <span>
                <strong>{money(decision.maximum_loss)}</strong>
                <small>max loss</small>
              </span>
              <StatusBadge verdict={decision.verdict} />
            </button>
          ))}
        </div>
        <DecisionDetail
          decision={selectedDecision}
          isApproved={isApproved}
          onApprove={onApprove}
          onVeto={onVeto}
          approval={approval}
          onSubmit={onSubmit}
          busy={busy}
          mode={mode}
        />
      </section>
    </div>
  );
}

function DecisionDetail({
  decision,
  isApproved,
  onApprove,
  onVeto,
  approval,
  onSubmit,
  busy,
  mode,
}: {
  decision?: PersonalDecision;
  isApproved: boolean;
  onApprove: () => void;
  onVeto: () => void;
  approval: {
    approval_id: string;
    expires_at: string;
    quantity: number;
    maximum_loss: string;
  } | null;
  onSubmit: () => void;
  busy: boolean;
  mode: "recorded" | "paper";
}) {
  if (!decision)
    return (
      <div className="panel detail-panel">
        <EmptyState title="No decision selected" detail="Run a scan to create a decision card." />
      </div>
    );
  const item = decision.payload;
  return (
    <div className="panel detail-panel">
      <div className="detail-top">
        <div>
          <span className="eyebrow accent">
            {item.underlying_symbol} ·{" "}
            {item.source === "bundled_fixture" ? "Recorded decision" : "Paper decision"}
          </span>
          <h3>Jury odds vs. market hurdle</h3>
        </div>
        <StatusBadge verdict={decision.verdict} />
      </div>
      <div className="juror-grid">
        {item.forecasts.map((forecast) => (
          <article className="juror-card" key={forecast.forecast_id}>
            <div className="juror-title">
              <span>{jurorNames[forecast.juror_id] ?? forecast.juror_id}</span>
              <small>{forecast.evidence_ids.length} refs</small>
            </div>
            <strong>{percent(forecast.probability)}</strong>
            <div className="juror-meta">
              <span>
                Calibration <b>{percent(forecast.calibration_score)}</b>
              </span>
              <span>
                Stake <b>{percent(forecast.confidence_stake)}</b>
              </span>
            </div>
            <p>{forecast.rationale}</p>
          </article>
        ))}
      </div>
      <div className="decision-metrics">
        <Metric label="Calibrated jury odds" value={percent(item.strategy.jury_probability)} />
        <Metric label="Option hurdle" value={percent(item.strategy.market_hurdle)} />
        <Metric
          label="Probability edge"
          value={`${Number(item.strategy.probability_edge) >= 0 ? "+" : ""}${percent(item.strategy.probability_edge, " pp")}`}
          accent={Number(item.strategy.probability_edge) >= 0 ? "positive" : "negative"}
        />
      </div>
      <OddsComparison
        juryProbability={item.strategy.jury_probability}
        hurdle={item.strategy.market_hurdle}
      />
      <div className="detail-columns">
        <div>
          <span className="eyebrow">Defined risk</span>
          <h4>Selected option legs</h4>
          <ul className="leg-list">
            {item.intent.legs.map((leg) => (
              <li key={leg.occ_symbol}>
                <code>{leg.occ_symbol}</code>
                <span>
                  {leg.position_intent.replaceAll("_", " ")} · qty {leg.quantity}
                </span>
              </li>
            ))}
          </ul>
          <p className="muted-copy">
            Net debit {money(item.strategy.net_debit)} · width {money(item.strategy.spread_width)} ·{" "}
            {item.intent.direction} intent
          </p>
        </div>
        <div className="record-box">
          <span className="eyebrow">Decision record</span>
          <h4>
            {isApproved ? "Approved after deterministic resize" : "Trade vetoed — no order sent"}
          </h4>
          <p>{item.verdict.reasons[0]}</p>
          {isApproved && item.pnl_snapshots?.length ? (
            <div className="record-stats">
              <Metric label="Order status" value={item.executions?.at(-1)?.status ?? "filled"} />
              <Metric
                label="Paper P&L"
                value={`${Number(item.pnl_snapshots.at(-1)?.unrealized_pnl ?? "0") >= 0 ? "+" : ""}${money(item.pnl_snapshots.at(-1)?.unrealized_pnl ?? "0")}`}
                accent="positive"
              />
            </div>
          ) : !isApproved ? (
            <div className="blocked-note">
              No approval artifact, Alpaca order, execution record, or P&amp;L follows this veto.
            </div>
          ) : null}
        </div>
      </div>
      <div className="detail-actions">
        {isApproved && !approval && (
          <button
            className="button button-primary"
            type="button"
            onClick={onApprove}
            disabled={busy || decision.status === "vetoed"}
          >
            Approve for paper order
          </button>
        )}
        {!isApproved && (
          <button className="button button-ghost" type="button" onClick={onVeto} disabled={busy}>
            Confirm veto
          </button>
        )}
        {approval && (
          <div className="approval-banner">
            <div>
              <strong>Approval ready · {approval.quantity} contract</strong>
              <span>
                Max loss {money(approval.maximum_loss)} · expires {shortTime(approval.expires_at)}
              </span>
            </div>
            <button
              className="button button-primary"
              type="button"
              onClick={onSubmit}
              disabled={busy || mode === "recorded"}
            >
              {mode === "recorded" ? "Paper mode required" : "Confirm & submit"}
            </button>
          </div>
        )}
      </div>
      <p className="disclaimer">
        Paper trading is simulated and does not represent future results. RiskCourt is not
        investment advice.
      </p>
    </div>
  );
}

function PortfolioView({
  portfolio,
  chartData,
  decisions,
}: {
  portfolio: Portfolio;
  chartData: Array<{ name: string; pnl: number }>;
  decisions: PersonalDecision[];
}) {
  return (
    <div className="view-stack">
      <section className="metric-grid">
        <MetricCard
          label="Account equity"
          value={portfolio.account.equity ? money(portfolio.account.equity) : "—"}
          detail="Paper account"
          tone="cyan"
        />
        <MetricCard
          label="Open positions"
          value={String(portfolio.positions.length)}
          detail="Live local records"
          tone="violet"
        />
        <MetricCard
          label="Pending orders"
          value={String(portfolio.orders.filter((item) => item.status === "submitted").length)}
          detail="Idempotency protected"
          tone="amber"
        />
        <MetricCard
          label="Realized P&L"
          value={money(
            decisions.reduce(
              (total, item) =>
                total + Number(item.payload?.pnl_snapshots?.at(-1)?.realized_pnl ?? 0),
              0,
            ),
          )}
          detail="From stored decisions"
          tone="green"
        />
      </section>
      <section className="content-grid">
        <div className="panel chart-panel">
          <PanelHeader eyebrow="Portfolio curve" title="P&L over decisions" />
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height={260}>
              <AreaChart data={chartData}>
                <CartesianGrid stroke="#ffffff12" vertical={false} />
                <XAxis dataKey="name" stroke="#64748b" />
                <YAxis stroke="#64748b" />
                <Tooltip
                  contentStyle={{
                    background: "#111827",
                    border: "1px solid #ffffff1c",
                    borderRadius: 12,
                  }}
                  formatter={(value) => [money(String(value)), "P&L"]}
                />
                <Area type="monotone" dataKey="pnl" stroke="#a78bfa" fill="#a78bfa22" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="panel">
          <PanelHeader eyebrow="Broker lifecycle" title="Orders" />
          {portfolio.orders.length ? (
            portfolio.orders.map((order) => (
              <div className="order-row" key={order.order_id}>
                <span>
                  <strong>{order.safe_reference ?? "Paper order"}</strong>
                  <small>{order.client_order_id}</small>
                </span>
                <StatusBadge verdict={order.status} label={order.status} />
              </div>
            ))
          ) : (
            <EmptyState
              title="No paper orders yet"
              detail="Approve a fresh decision when the account and market gates are green."
            />
          )}
        </div>
      </section>
    </div>
  );
}

function JournalView({
  journal,
  selectedDecision,
  onAdd,
}: {
  journal: JournalEntry[];
  selectedDecision?: PersonalDecision;
  onAdd: (body: string) => Promise<void>;
}) {
  const [body, setBody] = useState("");
  return (
    <div className="view-stack journal-layout">
      <section className="panel journal-editor">
        <PanelHeader eyebrow="Private research log" title="What are you seeing?" />
        <textarea
          value={body}
          onChange={(event) => setBody(event.target.value)}
          placeholder="Capture the thesis, invalidation, or what you would do differently…"
          rows={6}
        />
        <div className="editor-footer">
          <span className="muted-label">
            {selectedDecision
              ? `Linked to ${selectedDecision.symbol} decision`
              : "No decision selected"}
          </span>
          <button
            className="button button-primary"
            type="button"
            onClick={() => {
              void onAdd(body);
              setBody("");
            }}
            disabled={!body.trim()}
          >
            Save note
          </button>
        </div>
      </section>
      <section className="panel journal-list">
        <PanelHeader eyebrow="History" title="Recent notes" />
        {journal.length ? (
          journal.map((entry) => (
            <article className="journal-entry" key={entry.entry_id}>
              <p>{entry.body}</p>
              <small>
                {new Date(entry.created_at).toLocaleString()}{" "}
                {entry.decision_id ? `· ${entry.decision_id}` : ""}
              </small>
            </article>
          ))
        ) : (
          <EmptyState
            title="Your journal is quiet"
            detail="Notes stay local and can be linked to a decision for later review."
          />
        )}
      </section>
    </div>
  );
}

function SettingsView({
  watchlist,
  onToggle,
  killSwitch,
  onToggleKillSwitch,
}: {
  watchlist: string[];
  onToggle: (symbol: string) => Promise<void>;
  killSwitch: boolean;
  onToggleKillSwitch: () => void;
}) {
  return (
    <div className="view-stack settings-layout">
      <section className="panel settings-panel">
        <PanelHeader
          eyebrow="Personal universe"
          title="Watchlist"
          action={<span className="muted-label">Small by design</span>}
        />
        <p className="muted-copy">
          RiskCourt V1 keeps the universe bounded to liquid underlyings with defined-risk option
          support.
        </p>
        <div className="symbol-grid">
          {["SPY", "QQQ"].map((symbol) => (
            <button
              key={symbol}
              type="button"
              className={`symbol-toggle ${watchlist.includes(symbol) ? "selected" : ""}`}
              onClick={() => void onToggle(symbol)}
            >
              <span>{symbol}</span>
              <small>{watchlist.includes(symbol) ? "Monitoring" : "Add to watchlist"}</small>
            </button>
          ))}
        </div>
      </section>
      <section className="panel settings-panel">
        <PanelHeader
          eyebrow="Execution guardrail"
          title="Kill switch"
          action={
            <span className={`state-label ${killSwitch ? "danger" : "safe"}`}>
              {killSwitch ? "Enabled" : "Armed"}
            </span>
          }
        />
        <p className="muted-copy">
          When enabled, new paper entries are blocked. Risk-reducing exits remain available after a
          fresh preview.
        </p>
        <button
          type="button"
          className={`button ${killSwitch ? "button-primary" : "button-danger"}`}
          onClick={onToggleKillSwitch}
        >
          {killSwitch ? "Resume new entries" : "Pause new entries"}
        </button>
      </section>
      <section className="panel settings-panel">
        <PanelHeader eyebrow="Runtime contract" title="Paper only, always" />
        <div className="contract-list">
          <span>
            <i className="check-icon">✓</i> Alpaca paper endpoint only
          </span>
          <span>
            <i className="check-icon">✓</i> Explicit approval before every order
          </span>
          <span>
            <i className="check-icon">✓</i> Three jurors cannot change position size
          </span>
          <span>
            <i className="check-icon">✓</i> Local secrets never enter the UI or audit export
          </span>
        </div>
      </section>
    </div>
  );
}

function PanelHeader({
  eyebrow,
  title,
  action,
}: {
  eyebrow: string;
  title: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="panel-header">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h3>{title}</h3>
      </div>
      {action}
    </div>
  );
}
function MetricCard({
  label,
  value,
  detail,
  tone,
}: {
  label: string;
  value: string;
  detail: string;
  tone: string;
}) {
  return (
    <div className={`metric-card ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
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
  return (
    <div className="metric">
      <span>{label}</span>
      <strong className={accent ?? ""}>{value}</strong>
    </div>
  );
}
function StatusBadge({ verdict, label }: { verdict: string; label?: string }) {
  const positive =
    verdict === "approve" ||
    verdict === "resize" ||
    verdict === "filled" ||
    verdict === "submitted";
  return (
    <span
      className={`status-badge ${positive ? "positive" : verdict === "veto" || verdict === "rejected" ? "negative" : "neutral"}`}
    >
      <i />
      {label ?? verdict}
    </span>
  );
}
function EmptyState({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="empty-state">
      <div className="empty-icon">·</div>
      <strong>{title}</strong>
      <p>{detail}</p>
    </div>
  );
}
function OddsComparison({ juryProbability, hurdle }: { juryProbability: string; hurdle: string }) {
  const jury = Math.max(0, Math.min(1, Number(juryProbability)));
  const market = Math.max(0, Math.min(1, Number(hurdle)));
  return (
    <div
      className="odds-comparison"
      role="img"
      aria-label={`Calibrated jury odds ${percent(juryProbability)} versus option-implied hurdle ${percent(hurdle)}`}
    >
      <div className="odds-labels">
        <span>
          Jury probability <b>{percent(juryProbability)}</b>
        </span>
        <span>
          Hurdle <b>{percent(hurdle)}</b>
        </span>
      </div>
      <div className="odds-track">
        <div className="odds-fill" style={{ width: `${jury * 100}%` }} />
        <div className="odds-marker" style={{ left: `${market * 100}%` }} />
      </div>
    </div>
  );
}

export default App;
