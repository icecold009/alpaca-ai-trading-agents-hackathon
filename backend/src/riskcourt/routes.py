"""Recorded-case API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from riskcourt.case_repository import RecordedCaseRepository, RecordedCaseSummary
from riskcourt.recorded_case import RecordedCase

router = APIRouter(prefix="/api/recorded-cases", tags=["recorded cases"])


def get_repository(request: Request) -> RecordedCaseRepository:
    repository: RecordedCaseRepository = request.app.state.recorded_case_repository
    return repository


RepositoryDependency = Annotated[RecordedCaseRepository, Depends(get_repository)]


@router.get("", response_model=tuple[RecordedCaseSummary, ...])
def list_recorded_cases(
    repository: RepositoryDependency,
) -> tuple[RecordedCaseSummary, ...]:
    return repository.list_summaries()


@router.get("/{case_id}", response_model=RecordedCase)
def get_recorded_case(
    case_id: str,
    repository: RepositoryDependency,
) -> RecordedCase:
    case = repository.get(case_id)
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recorded case not found",
        )
    return case
