"""Independent, evidence-bound juror contracts; jurors cannot create orders."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from pydantic import Field

from riskcourt.domain import ContractModel, EvidenceIds, ForecastOutcome, ProbabilityForecast
from riskcourt.model_provider import (
    ProviderBoundary,
    ProviderReply,
    ProviderRequest,
    ProviderUnavailable,
)


@dataclass(frozen=True, slots=True)
class JurorSpec:
    juror_id: str
    specialty: str


JUROR_SPECS = (
    JurorSpec("juror_market", "price and market structure"),
    JurorSpec("juror_catalyst", "news and catalysts"),
    JurorSpec("juror_volatility", "volatility and options structure"),
)


class JurorOutput(ContractModel):
    probability: Decimal = Field(ge=0, le=1)
    calibration_score: Decimal = Field(ge=0, le=1)
    confidence_stake: Decimal = Field(ge=0, le=1)
    evidence_ids: EvidenceIds
    rationale: str = Field(min_length=1, max_length=2000)
    invalidation: str = Field(min_length=1, max_length=1000)


def run_juror(
    boundary: ProviderBoundary,
    spec: JurorSpec,
    *,
    case_id: str,
    outcome: ForecastOutcome,
    produced_at: datetime,
    horizon_at: datetime,
    available_evidence_ids: tuple[str, ...],
    model_version: str = "stub-v1",
    prompt_version: str = "jury-v1",
) -> ProbabilityForecast:
    request = ProviderRequest(
        request_id=f"request_{spec.juror_id}",
        prompt_version=prompt_version,
        model_version=model_version,
        payload={
            "juror_id": spec.juror_id,
            "specialty": spec.specialty,
            "case_id": case_id,
            "outcome": outcome.value,
            "available_evidence_ids": list(available_evidence_ids),
        },
    )
    result = boundary.call(request, JurorOutput)
    output = result.data
    if not set(output.evidence_ids).issubset(available_evidence_ids):
        raise ProviderUnavailable("juror cited evidence outside the supplied boundary")
    return ProbabilityForecast(
        forecast_id=f"forecast_{spec.juror_id.removeprefix('juror_')}",
        case_id=case_id,
        juror_id=spec.juror_id,
        outcome=outcome,
        probability=output.probability,
        calibration_score=output.calibration_score,
        confidence_stake=output.confidence_stake,
        produced_at=produced_at,
        horizon_at=horizon_at,
        evidence_ids=output.evidence_ids,
        rationale=output.rationale,
        invalidation=output.invalidation,
        model_version=model_version,
        prompt_version=prompt_version,
    )


class DeterministicJurorStub:
    """Offline provider for recorded demos and contract tests."""

    def complete(self, request: ProviderRequest) -> ProviderReply:
        juror_id = str(request.payload["juror_id"])
        probabilities = {
            "juror_market": "0.62",
            "juror_catalyst": "0.58",
            "juror_volatility": "0.60",
        }
        return ProviderReply(
            output={
                "probability": probabilities[juror_id],
                "calibration_score": "0.80",
                "confidence_stake": "0.70",
                "evidence_ids": request.payload["available_evidence_ids"],
                "rationale": f"Deterministic {juror_id} stub rationale",
                "invalidation": "Invalidate if the supplied evidence becomes stale.",
            }
        )
