"""Filesystem repository for validated recorded cases."""

from pathlib import Path

from riskcourt.domain import ContractModel, Identifier, Ticker, VerdictDecision
from riskcourt.recorded_case import RecordedCase

def _default_cases_dir() -> Path:
    """Find checked-in fixtures from both a source checkout and an installed app."""

    relative_path = Path("fixtures") / "cases"
    search_roots = (Path.cwd(), *Path.cwd().parents, *Path(__file__).resolve().parents)
    for root in search_roots:
        candidate = root / relative_path
        if candidate.is_dir():
            return candidate
    return Path.cwd() / relative_path


DEFAULT_CASES_DIR = _default_cases_dir()


class RecordedCaseSummary(ContractModel):
    case_id: Identifier
    name: str
    underlying_symbol: Ticker
    decision: VerdictDecision


class RecordedCaseRepository:
    def __init__(self, cases_dir: Path = DEFAULT_CASES_DIR) -> None:
        self._cases_dir = cases_dir

    def list_cases(self) -> tuple[RecordedCase, ...]:
        return tuple(
            sorted(
                (
                    RecordedCase.model_validate_json(path.read_text(encoding="utf-8"))
                    for path in self._cases_dir.glob("*.json")
                ),
                key=lambda case: case.case_id,
            )
        )

    def list_summaries(self) -> tuple[RecordedCaseSummary, ...]:
        return tuple(
            RecordedCaseSummary(
                case_id=case.case_id,
                name=case.name,
                underlying_symbol=case.underlying_symbol,
                decision=case.verdict.decision,
            )
            for case in self.list_cases()
        )

    def get(self, case_id: str) -> RecordedCase | None:
        return next((case for case in self.list_cases() if case.case_id == case_id), None)
