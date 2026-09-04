import type { RecordedCaseView } from "./recordedCases";

/** Optional hosted API boundary; an unavailable backend always falls back to fixtures. */
export function runtimeApiBaseUrl(
  configured = import.meta.env.VITE_RISKCOURT_API_URL,
): string | null {
  const trimmed = configured?.trim();
  if (!trimmed) return null;

  try {
    const parsed = new URL(trimmed);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return null;
    return parsed.toString().replace(/\/+$/, "");
  } catch {
    return null;
  }
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
    if (!Array.isArray(summaries)) {
      return null;
    }
    const rawCaseIds = summaries.map((item) => item.case_id);
    if (
      rawCaseIds.some((caseId) => typeof caseId !== "string") ||
      new Set(rawCaseIds).size !== rawCaseIds.length
    ) {
      return null;
    }
    const caseIds = rawCaseIds as string[];
    const responses = await Promise.all(
      caseIds.map((caseId) =>
        fetcher(`${baseUrl}/api/recorded-cases/${encodeURIComponent(caseId)}`, {
          headers: { Accept: "application/json" },
        }),
      ),
    );
    if (responses.some((response) => !response.ok)) return null;
    const cases = await Promise.all(responses.map((response) => response.json()));
    return cases.every(
      (value, index) => isRecordedCaseView(value) && value.case_id === caseIds[index],
    )
      ? (cases as RecordedCaseView[])
      : null;
  } catch {
    return null;
  }
}

function isRecordedCaseView(value: unknown): value is RecordedCaseView {
  if (!isRecord(value)) return false;
  const candidate = value as Partial<RecordedCaseView>;
  return (
    isNonEmptyString(candidate.case_id) &&
    isNonEmptyString(candidate.name) &&
    isNonEmptyString(candidate.underlying_symbol) &&
    isTimestamp(candidate.as_of) &&
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
    isNonEmptyString(value.forecast_id) &&
    isNonEmptyString(value.juror_id) &&
    isProbability(value.probability) &&
    isProbability(value.calibration_score) &&
    isProbability(value.confidence_stake) &&
    Array.isArray(value.evidence_ids) &&
    value.evidence_ids.every(isNonEmptyString) &&
    isNonEmptyString(value.rationale)
  );
}

function isStrategy(value: unknown): value is RecordedCaseView["strategy"] {
  if (!isRecord(value)) return false;
  return (
    isProbability(value.jury_probability) &&
    isProbability(value.market_hurdle) &&
    isNumber(value.probability_edge) &&
    isNonNegativeNumber(value.minimum_edge) &&
    isNonNegativeNumber(value.net_debit) &&
    isNonNegativeNumber(value.spread_width)
  );
}

function isIntent(value: unknown): value is RecordedCaseView["intent"] {
  if (!isRecord(value) || (value.direction !== "bullish" && value.direction !== "bearish")) {
    return false;
  }
  return (
    isNonNegativeNumber(value.maximum_loss) &&
    Array.isArray(value.legs) &&
    value.legs.every(
      (leg) =>
        isRecord(leg) &&
        isNonEmptyString(leg.occ_symbol) &&
        isNonEmptyString(leg.position_intent) &&
        isPositiveInteger(leg.quantity) &&
        isNonNegativeNumber(leg.strike),
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
    isNonNegativeInteger(value.approved_quantity) &&
    isNonNegativeNumber(value.maximum_loss) &&
    Array.isArray(value.reasons) &&
    value.reasons.every(isNonEmptyString)
  );
}

function isApproval(value: unknown): value is NonNullable<RecordedCaseView["approval"]> {
  return (
    isRecord(value) &&
    isPositiveInteger(value.approved_quantity) &&
    isNonNegativeNumber(value.maximum_loss)
  );
}

function isExecution(value: unknown): value is RecordedCaseView["executions"][number] {
  return (
    isRecord(value) &&
    isNonEmptyString(value.client_order_id) &&
    isNonEmptyString(value.status) &&
    (value.filled_debit === null || isNonNegativeNumber(value.filled_debit))
  );
}

function isPnlSnapshot(value: unknown): value is RecordedCaseView["pnl_snapshots"][number] {
  return (
    isRecord(value) &&
    isNonNegativeNumber(value.position_value) &&
    isNonNegativeNumber(value.cost_basis) &&
    isNumber(value.unrealized_pnl) &&
    isNumber(value.realized_pnl)
  );
}

function isTimestamp(value: unknown): value is string {
  return typeof value === "string" && Number.isFinite(Date.parse(value));
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim() !== "";
}

function isNumber(value: unknown): value is string {
  return typeof value === "string" && value.trim() !== "" && Number.isFinite(Number(value));
}

function isNonNegativeNumber(value: unknown): value is string {
  return isNumber(value) && Number(value) >= 0;
}

function isProbability(value: unknown): value is string {
  return isNumber(value) && Number(value) >= 0 && Number(value) <= 1;
}

function isPositiveInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value > 0;
}

function isNonNegativeInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}
