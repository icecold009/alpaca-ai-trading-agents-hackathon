import type { RecordedCaseView } from "./recordedCases";

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

export type Portfolio = {
  account: AccountSummary;
  positions: Array<Record<string, string>>;
  orders: Array<Record<string, string>>;
  kill_switch: { enabled: boolean; reason: string; updated_at: string };
};

export type JournalEntry = {
  entry_id: string;
  decision_id: string | null;
  body: string;
  created_at: string;
  updated_at: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      typeof body?.detail === "string" ? body.detail : `Request failed (${response.status})`,
    );
  }
  return (await response.json()) as T;
}

export const personalApi = {
  account: () => request<AccountSummary>("/api/account/summary"),
  portfolio: () => request<Portfolio>("/api/portfolio"),
  watchlist: () =>
    request<{ symbols: Array<{ symbol: string; enabled: number }> }>("/api/watchlist"),
  decisions: () => request<{ decisions: PersonalDecision[] }>("/api/decisions"),
  journal: () => request<{ entries: JournalEntry[] }>("/api/journal"),
  scan: (symbols?: string[]) =>
    request<{
      decisions: PersonalDecision[];
      failures: Array<{ symbol: string; reason: string }>;
      scan_id: string;
    }>("/api/scans", { method: "POST", body: JSON.stringify(symbols ? { symbols } : {}) }),
  veto: (decisionId: string) =>
    request<PersonalDecision>(`/api/decisions/${decisionId}/veto`, { method: "POST" }),
  approve: (decisionId: string) =>
    request<{
      approval: { approval_id: string; expires_at: string; quantity: number; maximum_loss: string };
    }>(`/api/decisions/${decisionId}/approve`, { method: "POST" }),
  submit: (approvalId: string, idempotencyKey: string) =>
    request<{ order: Record<string, string>; replayed: boolean }>(
      `/api/approvals/${approvalId}/submit`,
      {
        method: "POST",
        body: JSON.stringify({ confirm: true, idempotency_key: idempotencyKey }),
      },
    ),
  journalEntry: (body: string, decisionId?: string) =>
    request<{ entry: JournalEntry }>("/api/journal", {
      method: "POST",
      body: JSON.stringify({ body, decision_id: decisionId ?? null }),
    }),
  saveWatchlist: (symbols: string[]) =>
    request<{ symbols: Array<{ symbol: string; enabled: number }> }>("/api/watchlist", {
      method: "POST",
      body: JSON.stringify({ symbols }),
    }),
  killSwitch: (enabled: boolean, reason: string) =>
    request<{ kill_switch: Portfolio["kill_switch"] }>("/api/kill-switch", {
      method: "POST",
      body: JSON.stringify({ enabled, reason }),
    }),
};
