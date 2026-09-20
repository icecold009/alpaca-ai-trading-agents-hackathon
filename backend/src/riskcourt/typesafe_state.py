"""Sanitized, role-scoped state sent to TypeSafe System One questions."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import datetime, timedelta

from pydantic import AwareDatetime, Field, JsonValue, model_validator

from riskcourt.domain import (
    ContractModel,
    EvidenceItem,
    EvidenceType,
    ForecastOutcome,
    Identifier,
    Ticker,
)

STATE_VERSION = "riskcourt-typesafe-state-v1"
MAX_EVIDENCE_AGE = timedelta(hours=24)
NO_SUPPORTED_EVIDENCE = "no_supported_evidence"


class TypeSafeEvidence(ContractModel):
    """Only the evidence fields needed for a bounded semantic judgment."""

    evidence_id: Identifier
    evidence_type: EvidenceType
    symbol: Ticker
    observed_at: AwareDatetime
    summary: str = Field(min_length=1, max_length=400)


class TypeSafeState(ContractModel):
    """Provider state with no account, order, credential, or raw-reference fields."""

    state_version: str = Field(default=STATE_VERSION, min_length=1, max_length=80)
    symbol: Ticker
    outcome: ForecastOutcome
    horizon_at: AwareDatetime
    as_of: AwareDatetime
    evidence: tuple[TypeSafeEvidence, ...]
    market: dict[str, JsonValue] = Field(default_factory=dict)
    options: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_sensitive_state_keys(self) -> TypeSafeState:
        """Reject sensitive fields before they can reach a provider."""

        for value in (self.market, self.options):
            _reject_sensitive_keys(value)
        return self

    @property
    def evidence_ids(self) -> tuple[str, ...]:
        return tuple(item.evidence_id for item in self.evidence)

    @property
    def state_hash(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def for_juror(self, juror_id: str) -> TypeSafeState:
        """Return the evidence partition allowed for one juror specialty."""

        allowed = _allowed_evidence_types(juror_id)
        scoped = tuple(item for item in self.evidence if item.evidence_type in allowed)
        return self.model_copy(update={"evidence": scoped})

    def validate_freshness(self, maximum_age: timedelta = MAX_EVIDENCE_AGE) -> None:
        """Reject future or stale observations using the code-owned observation clock."""

        for item in self.evidence:
            age = self.as_of - item.observed_at
            if age < timedelta(0):
                raise ValueError("evidence observation is from the future")
            if age > maximum_age:
                raise ValueError("evidence is stale")


def build_typesafe_state(
    *,
    symbol: str,
    outcome: ForecastOutcome,
    horizon_at: datetime,
    as_of: datetime,
    evidence: Iterable[EvidenceItem],
    market: dict[str, JsonValue] | None = None,
    options: dict[str, JsonValue] | None = None,
) -> TypeSafeState:
    """Convert domain evidence into a bounded provider state."""

    selected = tuple(
        TypeSafeEvidence(
            evidence_id=item.evidence_id,
            evidence_type=item.evidence_type,
            symbol=item.symbol,
            observed_at=item.observed_at,
            summary=item.summary,
        )
        for item in evidence
    )
    if len({item.evidence_id for item in selected}) != len(selected):
        raise ValueError("duplicate evidence IDs are not allowed")
    return TypeSafeState(
        symbol=symbol,
        outcome=outcome,
        horizon_at=horizon_at,
        as_of=as_of,
        evidence=selected,
        market=market or {},
        options=options or {},
    )


def _allowed_evidence_types(juror_id: str) -> frozenset[EvidenceType]:
    if juror_id == "juror_market":
        return frozenset({EvidenceType.UNDERLYING_QUOTE, EvidenceType.MARKET_BAR})
    if juror_id == "juror_volatility":
        return frozenset({EvidenceType.OPTION_QUOTE})
    if juror_id == "juror_catalyst":
        return frozenset({EvidenceType.NEWS})
    raise ValueError("unknown juror specialty")


def _reject_sensitive_keys(value: JsonValue, path: str = "state") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            lowered = key.lower()
            if any(
                token in lowered
                for token in ("api_key", "secret", "credential", "account_id", "order_id")
            ):
                raise ValueError(f"sensitive provider state key: {path}.{key}")
            _reject_sensitive_keys(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _reject_sensitive_keys(nested, f"{path}[{index}]")
