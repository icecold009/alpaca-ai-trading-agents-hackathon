import edgePositive from "../../fixtures/cases/edge-positive.json";
import insufficientEdge from "../../fixtures/cases/insufficient-edge.json";

export interface RecordedCaseView {
  case_id: string;
  name: string;
  underlying_symbol: string;
  as_of: string;
  forecasts: Array<{
    forecast_id: string;
    juror_id: string;
    probability: string;
    calibration_score: string;
    confidence_stake: string;
    evidence_ids: string[];
    rationale: string;
  }>;
  strategy: {
    jury_probability: string;
    market_hurdle: string;
    probability_edge: string;
    minimum_edge: string;
    net_debit: string;
    spread_width: string;
  };
  intent: {
    maximum_loss: string;
    direction: "bullish" | "bearish";
    legs: Array<{
      occ_symbol: string;
      position_intent: string;
      quantity: number;
      strike: string;
    }>;
  };
  verdict: {
    decision: "approve" | "resize" | "veto" | "abstain";
    approved_quantity: number;
    maximum_loss: string;
    reasons: string[];
  };
  approval: {
    approved_quantity: number;
    maximum_loss: string;
  } | null;
  executions: Array<{
    client_order_id: string;
    status: string;
    filled_debit: string | null;
  }>;
  pnl_snapshots: Array<{
    position_value: string;
    cost_basis: string;
    unrealized_pnl: string;
    realized_pnl: string;
  }>;
}

export const recordedCases = [edgePositive, insufficientEdge] as RecordedCaseView[];
