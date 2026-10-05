import type { RecordedCaseView } from "./recordedCases";
import { isRecordedCaseView, runtimeApiBaseUrl } from "./runtime";

export type Mode = "recorded" | "paper";

export type PersonalDecision = {
  decision_id: string;
  scan_id: string;
  case_id: string;
  mode: Mode;
  symbol: string;
  verdict: "approve" | "resize" | "veto" | "abstain";
  status: string;
  as_of: string;
  freshness_until: string;
  maximum_loss: string;
  created_at: string;
  payload: RecordedCaseView;
};

export type AccountSummary = {
  mode: Mode;
  paper: boolean;
  status: string;
  equity: string | null;
  buying_power: string | null;
  options_approved_level?: number | null;
  options_trading_level?: number | null;
  market_open: boolean;
  clock_timestamp?: string;
  next_open?: string;
  next_close?: string;
  position_count: number;
  pending_order_count: number;
  message?: string;
};

export type ExitPreview = {
  position_id: string;
  status: string;
  action: string;
  reason: string;
  confirm_required?: boolean;
  approval?: { approval_id: string; expires_at: string; quantity: number };
};

export type Portfolio = {
  account: AccountSummary;
  positions: Array<{
    position_id: string;
    decision_id: string;
    symbol?: string;
    status: string;
    quantity: string;
    cost_basis: string;
    position_value: string;
    unrealized_pnl: string;
    realized_pnl: string;
    mark_at: string | null;
    reconciliation_status: string;
    reconciliation_reason: string;
  }>;
  orders: Array<{
    order_id: string;
    safe_reference?: string | null;
    approval_id: string;
    client_order_id: string;
    status: string;
    filled_qty: string;
    filled_avg_price: string | null;
    submitted_at: string;
    updated_at: string | null;
  }>;
  kill_switch: { enabled: boolean; reason: string; updated_at: string };
  reconciliation?: {
    status: string;
    checked_orders?: number;
    updated_orders?: number;
    matched_positions?: number;
    discrepant_positions?: number;
    stale_marks?: number;
    unmapped_broker_option_legs?: number;
  };
};

export type JournalEntry = {
  entry_id: string;
  decision_id: string | null;
  body: string;
  created_at: string;
  updated_at: string;
};

type ResponseGuard<T> = (value: unknown) => value is T;

function apiBaseUrl() {
  const configured = import.meta.env.VITE_RISKCOURT_API_URL?.trim();
  if (!configured) return "";
  const validated = runtimeApiBaseUrl(configured);
  if (!validated) throw new Error("VITE_RISKCOURT_API_URL must be an HTTPS or loopback API origin");
  return validated;
}

async function request<T>(
  path: string,
  validate: ResponseGuard<T>,
  init?: RequestInit,
): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 10_000);
  try {
    const response = await fetch(`${apiBaseUrl()}${path}`, {
      ...init,
      signal: controller.signal,
      credentials: "omit",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
    });
    const body: unknown = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error(
        isRecord(body) && typeof body.detail === "string"
          ? body.detail
          : `Request failed (${response.status})`,
      );
    }
    if (!validate(body)) throw new Error("API returned an invalid response");
    return body;
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      throw new Error("API request timed out", { cause: error });
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isStringOrNull(value: unknown): value is string | null {
  return value === null || isString(value);
}

function hasStrings(value: unknown, keys: string[]): value is Record<string, unknown> {
  return isRecord(value) && keys.every((key) => isString(value[key]));
}

function isAccountSummary(value: unknown): value is AccountSummary {
  return (
    isRecord(value) &&
    (value.mode === "paper" || value.mode === "recorded") &&
    typeof value.paper === "boolean" &&
    isString(value.status) &&
    isStringOrNull(value.equity) &&
    isStringOrNull(value.buying_power) &&
    typeof value.market_open === "boolean" &&
    typeof value.position_count === "number" &&
    typeof value.pending_order_count === "number"
  );
}

function isPosition(value: unknown): value is Portfolio["positions"][number] {
  return (
    hasStrings(value, [
      "position_id",
      "decision_id",
      "status",
      "quantity",
      "cost_basis",
      "position_value",
      "unrealized_pnl",
      "realized_pnl",
      "reconciliation_status",
      "reconciliation_reason",
    ]) &&
    (value.mark_at === null || isString(value.mark_at))
  );
}

function isOrder(value: unknown): value is Portfolio["orders"][number] {
  return (
    hasStrings(value, [
      "order_id",
      "approval_id",
      "client_order_id",
      "status",
      "filled_qty",
      "submitted_at",
    ]) &&
    (value.safe_reference === null || isString(value.safe_reference)) &&
    isStringOrNull(value.filled_avg_price) &&
    isStringOrNull(value.updated_at)
  );
}

function isPortfolio(value: unknown): value is Portfolio {
  return (
    isRecord(value) &&
    isAccountSummary(value.account) &&
    Array.isArray(value.positions) &&
    value.positions.every(isPosition) &&
    Array.isArray(value.orders) &&
    value.orders.every(isOrder) &&
    isRecord(value.kill_switch) &&
    typeof value.kill_switch.enabled === "boolean" &&
    isString(value.kill_switch.reason) &&
    isString(value.kill_switch.updated_at)
  );
}

function isDecision(value: unknown): value is PersonalDecision {
  return (
    isRecord(value) &&
    hasStrings(value, [
      "decision_id",
      "scan_id",
      "case_id",
      "symbol",
      "verdict",
      "status",
      "as_of",
      "freshness_until",
      "maximum_loss",
      "created_at",
    ]) &&
    (value.mode === "paper" || value.mode === "recorded") &&
    isRecordedCaseView(value.payload)
  );
}

function isDecisionList(value: unknown): value is { decisions: PersonalDecision[] } {
  return isRecord(value) && Array.isArray(value.decisions) && value.decisions.every(isDecision);
}

function isWatchlist(
  value: unknown,
): value is { symbols: Array<{ symbol: string; enabled: number }> } {
  return (
    isRecord(value) &&
    Array.isArray(value.symbols) &&
    value.symbols.every(
      (item) =>
        isRecord(item) && isString(item.symbol) && (item.enabled === 0 || item.enabled === 1),
    )
  );
}

function isJournal(value: unknown): value is { entries: JournalEntry[] } {
  return (
    isRecord(value) &&
    Array.isArray(value.entries) &&
    value.entries.every(
      (item) =>
        isRecord(item) &&
        isString(item.entry_id) &&
        (item.decision_id === null || isString(item.decision_id)) &&
        isString(item.body) &&
        isString(item.created_at) &&
        isString(item.updated_at),
    )
  );
}

function isApproval(value: unknown): value is {
  approval: { approval_id: string; expires_at: string; quantity: number; maximum_loss: string };
} {
  return (
    isRecord(value) &&
    isRecord(value.approval) &&
    hasStrings(value.approval, ["approval_id", "expires_at", "maximum_loss"]) &&
    typeof value.approval.quantity === "number"
  );
}

function isSubmitResult(
  value: unknown,
): value is { order: Record<string, string>; replayed: boolean } {
  return isRecord(value) && isRecord(value.order) && typeof value.replayed === "boolean";
}

function isExitSubmitResult(
  value: unknown,
): value is { order: Portfolio["orders"][number]; replayed: boolean } {
  return isRecord(value) && isOrder(value.order) && typeof value.replayed === "boolean";
}

function isExitPreview(value: unknown): value is ExitPreview {
  return (
    hasStrings(value, ["position_id", "status", "action", "reason"]) &&
    (value.confirm_required === undefined || typeof value.confirm_required === "boolean") &&
    (value.approval === undefined ||
      (isRecord(value.approval) &&
        hasStrings(value.approval, ["approval_id", "expires_at"]) &&
        typeof value.approval.quantity === "number"))
  );
}

function isKillSwitchResult(value: unknown): value is { kill_switch: Portfolio["kill_switch"] } {
  return (
    isRecord(value) &&
    isRecord(value.kill_switch) &&
    typeof value.kill_switch.enabled === "boolean" &&
    isString(value.kill_switch.reason) &&
    isString(value.kill_switch.updated_at)
  );
}

export const personalApi = {
  account: () => request<AccountSummary>("/api/account/summary", isAccountSummary),
  portfolio: () => request<Portfolio>("/api/portfolio", isPortfolio),
  watchlist: () =>
    request<{ symbols: Array<{ symbol: string; enabled: number }> }>("/api/watchlist", isWatchlist),
  decisions: () => request<{ decisions: PersonalDecision[] }>("/api/decisions", isDecisionList),
  journal: () => request<{ entries: JournalEntry[] }>("/api/journal", isJournal),
  scan: (symbols?: string[]) =>
    request<{
      decisions: PersonalDecision[];
      failures: Array<{ symbol: string; reason: string }>;
      scan_id: string;
    }>(
      "/api/scans",
      (
        value,
      ): value is {
        decisions: PersonalDecision[];
        failures: Array<{ symbol: string; reason: string }>;
        scan_id: string;
      } =>
        isRecord(value) &&
        isString(value.scan_id) &&
        Array.isArray(value.decisions) &&
        value.decisions.every(isDecision) &&
        Array.isArray(value.failures) &&
        value.failures.every(
          (item) => isRecord(item) && isString(item.symbol) && isString(item.reason),
        ),
      { method: "POST", body: JSON.stringify(symbols ? { symbols } : {}) },
    ),
  veto: (decisionId: string) =>
    request<PersonalDecision>(`/api/decisions/${encodeURIComponent(decisionId)}/veto`, isDecision, {
      method: "POST",
    }),
  approve: (decisionId: string) =>
    request<{
      approval: { approval_id: string; expires_at: string; quantity: number; maximum_loss: string };
    }>(`/api/decisions/${encodeURIComponent(decisionId)}/approve`, isApproval, { method: "POST" }),
  submit: (approvalId: string) =>
    request<{ order: Record<string, string>; replayed: boolean }>(
      `/api/approvals/${encodeURIComponent(approvalId)}/submit`,
      isSubmitResult,
      {
        method: "POST",
        body: JSON.stringify({ confirm: true }),
      },
    ),
  reconcile: () =>
    request<NonNullable<Portfolio["reconciliation"]>>(
      "/api/reconcile",
      (value): value is NonNullable<Portfolio["reconciliation"]> =>
        isRecord(value) && isString(value.status),
      { method: "POST" },
    ),
  exitPreview: (positionId: string) =>
    request<ExitPreview>(
      `/api/positions/${encodeURIComponent(positionId)}/exit-preview`,
      isExitPreview,
      {
        method: "POST",
      },
    ),
  exitSubmit: (positionId: string) =>
    request<{ order: Portfolio["orders"][number]; replayed: boolean }>(
      `/api/positions/${encodeURIComponent(positionId)}/exit-submit`,
      isExitSubmitResult,
      { method: "POST", body: JSON.stringify({ confirm: true }) },
    ),
  journalEntry: (body: string, decisionId?: string) =>
    request<{ entry: JournalEntry }>(
      "/api/journal",
      (value): value is { entry: JournalEntry } =>
        isRecord(value) && isJournal({ entries: [value.entry] }),
      {
        method: "POST",
        body: JSON.stringify({ body, decision_id: decisionId ?? null }),
      },
    ),
  saveWatchlist: (symbols: string[]) =>
    request<{ symbols: Array<{ symbol: string; enabled: number }> }>(
      "/api/watchlist",
      isWatchlist,
      {
        method: "POST",
        body: JSON.stringify({ symbols }),
      },
    ),
  killSwitch: (enabled: boolean, reason: string) =>
    request<{ kill_switch: Portfolio["kill_switch"] }>("/api/kill-switch", isKillSwitchResult, {
      method: "POST",
      body: JSON.stringify({ enabled, reason }),
    }),
};
