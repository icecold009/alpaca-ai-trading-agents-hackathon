from pathlib import Path

import pytest
from pydantic import ValidationError

from riskcourt.evaluation import (
    EXPECTED_CASE_COUNT,
    EvaluationOutcome,
    EvaluationScenario,
    evaluation_summary,
    load_evaluation_set,
)


def test_fd045_evaluation_set_is_complete_and_balanced() -> None:
    evaluation_set = load_evaluation_set()

    assert len(evaluation_set.cases) == EXPECTED_CASE_COUNT
    assert {case.scenario for case in evaluation_set.cases} == set(EvaluationScenario)
    assert {case.expected_outcome for case in evaluation_set.cases} == set(EvaluationOutcome)
    assert evaluation_summary(evaluation_set) == {
        "version": "fd045-v1",
        "case_count": 12,
        "outcomes": {"abstain": 3, "error": 4, "trade": 2, "veto": 3},
        "unauthorized_order_attempts": 0,
        "unknown_evidence_cases": 1,
    }


def test_fd045_unknown_evidence_is_explicitly_rejected() -> None:
    evaluation_set = load_evaluation_set()
    case = next(
        case
        for case in evaluation_set.cases
        if case.scenario is EvaluationScenario.UNKNOWN_EVIDENCE
    )

    assert case.unknown_evidence_ids == ("evidence_unknown",)
    assert case.expected_outcome is EvaluationOutcome.ERROR
    assert case.expected_order_attempts == 0


@pytest.mark.parametrize(
    "patch",
    [
        {"cases": []},
        {
            "cases": [
                {
                    "case_id": "eval_bad",
                    "scenario": "no_edge",
                    "expected_outcome": "trade",
                    "evidence_ids": ["quote_spy"],
                    "description": "bad",
                }
            ]
        },
    ],
)
def test_fd045_rejects_incomplete_or_mismatched_sets(patch: dict[str, object]) -> None:
    payload = {"version": "fd045-test", "cases": patch["cases"]}

    with pytest.raises(ValidationError):
        from riskcourt.evaluation import EvaluationSet

        EvaluationSet.model_validate(payload)


def test_fd045_path_is_repo_relative_and_present() -> None:
    assert Path(load_evaluation_set.__globals__["DEFAULT_EVALUATION_PATH"]).is_file()
