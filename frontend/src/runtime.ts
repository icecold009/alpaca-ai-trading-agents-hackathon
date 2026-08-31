import type { RecordedCaseView } from "./recordedCases";

/** Optional hosted API boundary; an unavailable backend always falls back to fixtures. */
export function runtimeApiBaseUrl(
  configured = import.meta.env.VITE_RISKCOURT_API_URL,
): string | null {
  const trimmed = configured?.trim();
  return trimmed ? trimmed.replace(/\/$/, "") : null;
}

export async function loadRecordedCases(
  fetcher: typeof fetch = fetch,
  baseUrl: string | null = runtimeApiBaseUrl(),
): Promise<RecordedCaseView[] | null> {
  if (!baseUrl) return null;

  try {
    const summariesResponse = await fetcher(`${baseUrl}/api/recorded-cases`, {
      headers: { Accept: "application/json" },
    });
    if (!summariesResponse.ok) return null;
    const summaries = (await summariesResponse.json()) as Array<{ case_id?: unknown }>;
    if (!Array.isArray(summaries) || summaries.some((item) => typeof item.case_id !== "string")) {
      return null;
    }
    const responses = await Promise.all(
      summaries.map((item) =>
        fetcher(`${baseUrl}/api/recorded-cases/${encodeURIComponent(item.case_id as string)}`, {
          headers: { Accept: "application/json" },
        }),
      ),
    );
    if (responses.some((response) => !response.ok)) return null;
    const cases = await Promise.all(responses.map((response) => response.json()));
    return cases.every(isRecordedCaseView) ? (cases as RecordedCaseView[]) : null;
  } catch {
    return null;
  }
}

function isRecordedCaseView(value: unknown): value is RecordedCaseView {
  if (!isRecord(value)) return false;
  const candidate = value as Partial<RecordedCaseView>;
  return (
    typeof candidate.case_id === "string" &&
    typeof candidate.name === "string" &&
    typeof candidate.underlying_symbol === "string" &&
    typeof candidate.as_of === "string" &&
    Array.isArray(candidate.forecasts) &&
    candidate.forecasts.every(isForecast) &&
    isStrategy(candidate.strategy) &&
    isIntent(candidate.intent) &&
    isVerdict(candidate.verdict) &&
    (candidate.approval === null || isApproval(candidate.approval)) &&
    Array.isArray(candidate.executions) &&
    candidate.executions.every(isExecution) &&
    Array.isArray(candidate.pnl_snapshots) &&
    candidate.pnl_snapshots.every(isPnlSnapshot)
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isForecast(value: unknown): value is RecordedCaseView["forecasts"][number] {
  if (!isRecord(value)) return false;
  return (
    typeof value.forecast_id === "string" &&
    typeof value.juror_id === "string" &&
    typeof value.probability === "string" &&
    typeof value.calibration_score === "string" &&
    typeof value.confidence_stake === "string" &&
    Array.isArray(value.evidence_ids) &&
    value.evidence_ids.every((evidenceId) => typeof evidenceId === "string") &&
    typeof value.rationale === "string"
  );
}

function isStrategy(value: unknown): value is RecordedCaseView["strategy"] {
  if (!isRecord(value)) return false;
  return [
    "jury_probability",
    "market_hurdle",
    "probability_edge",
    "minimum_edge",
    "net_debit",
    "spread_width",
  ].every((field) => typeof value[field] === "string");
}

function isIntent(value: unknown): value is RecordedCaseView["intent"] {
  if (!isRecord(value) || (value.direction !== "bullish" && value.direction !== "bearish")) {
    return false;
  }
  return (
    typeof value.maximum_loss === "string" &&
    Array.isArray(value.legs) &&
    value.legs.every(
      (leg) =>
        isRecord(leg) &&
        typeof leg.occ_symbol === "string" &&
        typeof leg.position_intent === "string" &&
        typeof leg.quantity === "number" &&
        typeof leg.strike === "string",
    )
  );
}

function isVerdict(value: unknown): value is RecordedCaseView["verdict"] {
  if (
    !isRecord(value) ||
    !["approve", "resize", "veto", "abstain"].includes(String(value.decision))
  ) {
    return false;
  }
  return (
    typeof value.approved_quantity === "number" &&
    typeof value.maximum_loss === "string" &&
    Array.isArray(value.reasons) &&
    value.reasons.every((reason) => typeof reason === "string")
  );
}

function isApproval(value: unknown): value is NonNullable<RecordedCaseView["approval"]> {
  return (
    isRecord(value) &&
    typeof value.approved_quantity === "number" &&
    typeof value.maximum_loss === "string"
  );
}

function isExecution(value: unknown): value is RecordedCaseView["executions"][number] {
  return (
    isRecord(value) &&
    typeof value.client_order_id === "string" &&
    typeof value.status === "string" &&
    (typeof value.filled_debit === "string" || value.filled_debit === null)
  );
}

function isPnlSnapshot(value: unknown): value is RecordedCaseView["pnl_snapshots"][number] {
  return (
    isRecord(value) &&
    typeof value.position_value === "string" &&
    typeof value.cost_basis === "string" &&
    typeof value.unrealized_pnl === "string" &&
    typeof value.realized_pnl === "string"
  );
}
