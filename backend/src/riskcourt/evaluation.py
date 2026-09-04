"""Credential-free evaluation cases for the bounded agent committee."""

from __future__ import annotations

import json
from collections import Counter
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Self

from pydantic import Field, model_validator

from riskcourt.domain import ContractModel, EvidenceIds, Identifier


def _default_evaluation_path() -> Path:
    """Find the checked-in evaluation set from both source and installed layouts."""

    relative_path = Path("fixtures") / "evaluation" / "fd045.json"
    search_roots = (Path.cwd(), *Path.cwd().parents, *Path(__file__).resolve().parents)
    for root in search_roots:
        candidate = root / relative_path
        if candidate.is_file():
            return candidate
    return Path.cwd() / relative_path


DEFAULT_EVALUATION_PATH = _default_evaluation_path()
EXPECTED_CASE_COUNT = 12


class EvaluationOutcome(StrEnum):
    TRADE = "trade"
    ABSTAIN = "abstain"
    VETO = "veto"
    ERROR = "error"


class EvaluationScenario(StrEnum):
    POSITIVE_EDGE = "positive_edge"
    RESIZE_EDGE = "resize_edge"
    STALE_QUOTE = "stale_quote"
    ILLIQUID_MARKET = "illiquid_market"
    NO_EDGE = "no_edge"
    JUROR_DISAGREEMENT = "juror_disagreement"
    PROMPT_INJECTION = "prompt_injection"
    DUPLICATE_INTENT = "duplicate_intent"
    DRAWDOWN_LIMIT = "drawdown_limit"
    PROVIDER_OUTAGE = "provider_outage"
    UNKNOWN_EVIDENCE = "unknown_evidence"
    MISSING_QUOTE = "missing_quote"


EXPECTED_OUTCOMES: dict[EvaluationScenario, EvaluationOutcome] = {
    EvaluationScenario.POSITIVE_EDGE: EvaluationOutcome.TRADE,
    EvaluationScenario.RESIZE_EDGE: EvaluationOutcome.TRADE,
    EvaluationScenario.STALE_QUOTE: EvaluationOutcome.ABSTAIN,
    EvaluationScenario.ILLIQUID_MARKET: EvaluationOutcome.VETO,
    EvaluationScenario.NO_EDGE: EvaluationOutcome.ABSTAIN,
    EvaluationScenario.JUROR_DISAGREEMENT: EvaluationOutcome.ABSTAIN,
    EvaluationScenario.PROMPT_INJECTION: EvaluationOutcome.ERROR,
    EvaluationScenario.DUPLICATE_INTENT: EvaluationOutcome.VETO,
    EvaluationScenario.DRAWDOWN_LIMIT: EvaluationOutcome.VETO,
    EvaluationScenario.PROVIDER_OUTAGE: EvaluationOutcome.ERROR,
    EvaluationScenario.UNKNOWN_EVIDENCE: EvaluationOutcome.ERROR,
    EvaluationScenario.MISSING_QUOTE: EvaluationOutcome.ERROR,
}


class EvaluationCase(ContractModel):
    """One dry-run case with a policy outcome and no order authority."""

    case_id: Identifier
    scenario: EvaluationScenario
    expected_outcome: EvaluationOutcome
    evidence_ids: EvidenceIds
    unknown_evidence_ids: tuple[Identifier, ...] = ()
    expected_order_attempts: Annotated[int, Field(ge=0)] = 0
    description: Annotated[str, Field(min_length=1, max_length=240)]

    @model_validator(mode="after")
    def validate_expected_policy(self) -> Self:
        expected = EXPECTED_OUTCOMES[self.scenario]
        if self.expected_outcome is not expected:
            raise ValueError(
                f"scenario {self.scenario.value} must resolve to {expected.value}, "
                f"not {self.expected_outcome.value}"
            )
        if self.unknown_evidence_ids and self.scenario is not EvaluationScenario.UNKNOWN_EVIDENCE:
            raise ValueError("unknown evidence is only permitted in the unknown_evidence case")
        if self.scenario is EvaluationScenario.UNKNOWN_EVIDENCE and not self.unknown_evidence_ids:
            raise ValueError("unknown_evidence must identify at least one rejected evidence ID")
        if self.expected_order_attempts != 0:
            raise ValueError("evaluation cases are dry-run and cannot authorize order attempts")
        return self


class EvaluationSet(ContractModel):
    """The frozen FD-045 set; execution is intentionally outside this contract."""

    version: Annotated[str, Field(min_length=1, max_length=40)]
    cases: Annotated[
        tuple[EvaluationCase, ...],
        Field(min_length=EXPECTED_CASE_COUNT, max_length=EXPECTED_CASE_COUNT),
    ]

    @model_validator(mode="after")
    def validate_complete_set(self) -> Self:
        case_ids = [case.case_id for case in self.cases]
        if len(set(case_ids)) != EXPECTED_CASE_COUNT:
            raise ValueError("evaluation case IDs must be unique")
        scenarios = {case.scenario for case in self.cases}
        if scenarios != set(EXPECTED_OUTCOMES):
            raise ValueError("evaluation set must cover every required scenario exactly once")
        outcomes = Counter(case.expected_outcome for case in self.cases)
        if any(outcomes[outcome] == 0 for outcome in EvaluationOutcome):
            raise ValueError("evaluation set must include trade, abstain, veto, and error outcomes")
        return self


def load_evaluation_set(path: Path = DEFAULT_EVALUATION_PATH) -> EvaluationSet:
    """Load and strictly validate the checked-in, credential-free evaluation set."""

    return EvaluationSet.model_validate_json(path.read_text(encoding="utf-8"))


def validate_evaluation_set(path: Path = DEFAULT_EVALUATION_PATH) -> EvaluationSet:
    """Return the validated set for CI and scripts; no external calls are made."""

    return load_evaluation_set(path)


def evaluation_summary(evaluation_set: EvaluationSet) -> dict[str, object]:
    """Produce a small machine-readable summary suitable for verification logs."""

    outcomes = Counter(case.expected_outcome.value for case in evaluation_set.cases)
    return {
        "version": evaluation_set.version,
        "case_count": len(evaluation_set.cases),
        "outcomes": dict(sorted(outcomes.items())),
        "unauthorized_order_attempts": sum(
            case.expected_order_attempts for case in evaluation_set.cases
        ),
        "unknown_evidence_cases": sum(
            bool(case.unknown_evidence_ids) for case in evaluation_set.cases
        ),
    }


def load_evaluation_set_from_json(raw: str) -> EvaluationSet:
    """Parse JSON supplied by a test or caller without touching the filesystem."""

    return EvaluationSet.model_validate(json.loads(raw))
