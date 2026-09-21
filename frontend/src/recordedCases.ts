import edgePositive from "../../fixtures/cases/edge-positive.json";
import insufficientEdge from "../../fixtures/cases/insufficient-edge.json";

type TypeSafeAnswers = {
  outcome_probability?: { noul?: string; margin?: string };
  evidence_anchor?: {
    choice?: string;
    confidence?: string;
    probabilities?: Record<string, string>;
  };
  evidence_quality?: {
    score?: string;
    confidence?: string;
    probabilities?: Record<string, string>;
  };
};

type TypeSafeTrace = {
  status?: string;
  reason?: string;
  probability?: string;
  evidence_ids?: string[];
  confidence_stake?: string;
  provider?: string;
  model?: string;
  question_set_version?: string;
  state_hash?: string;
  evidence_types?: string[];
  evidence_quality?: string;
  minimum_evidence_quality?: string;
  noul_probability?: string;
  noul_margin?: string;
  heuristic_confidence?: string;
  typesafe_confidence?: string;
  typesafe_answers?: TypeSafeAnswers;
  input_tokens?: number;
  output_tokens?: number;
  latency_ms?: number;
  validation?: string;
};

export interface RecordedCaseView {
  case_id: string;
  name: string;
  source?: string;
  underlying_symbol: string;
  as_of: string;
  juror_abstentions?: Array<{ juror_id: string; reason: string }>;
  forecasts: Array<{
    forecast_id: string;
    juror_id: string;
    probability: string;
    calibration_score: string;
    confidence_stake: string;
    evidence_ids: string[];
    rationale: string;
    provider_metadata?: {
      status?: string;
      reason?: string;
      provider?: string;
      model?: string;
      question_set_version?: string;
      state_hash?: string;
      evidence_types?: string[];
      typesafe_confidence?: string;
      evidence_quality?: string;
      minimum_evidence_quality?: string;
      noul_probability?: string;
      noul_margin?: string;
      heuristic_confidence?: string;
      typesafe_answers?: TypeSafeAnswers;
      input_tokens?: number;
      output_tokens?: number;
      latency_ms?: number;
      validation?: string;
      shadow_typesafe?: TypeSafeTrace;
    };
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
