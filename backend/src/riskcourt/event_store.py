"""Hash-chained decision events, replay projection, and sanitized export."""

import hashlib
from decimal import Decimal
from typing import Self

from pydantic import Field, JsonValue, TypeAdapter

from riskcourt.domain import (
    ContractModel,
    DecisionEvent,
    DecisionEventType,
    Identifier,
)

SHA256_PATTERN = r"^[0-9a-f]{64}$"


class ChainedDecisionEvent(ContractModel):
    event: DecisionEvent
    previous_hash: str | None
    event_hash: str = Field(pattern=SHA256_PATTERN)


class DecisionProjection(ContractModel):
    case_id: Identifier
    last_sequence: int
    last_event_type: DecisionEventType
    approval_id: str | None = None
    execution_status: str | None = None
    unrealized_pnl: Decimal | None = None


class DecisionCard(ContractModel):
    case_id: Identifier
    head_hash: str = Field(pattern=SHA256_PATTERN)
    projection: DecisionProjection
    events: tuple[DecisionEvent, ...]


CHAIN_ADAPTER = TypeAdapter(tuple[ChainedDecisionEvent, ...])


class AppendOnlyDecisionLog:
    def __init__(self, case_id: str) -> None:
        self.case_id = case_id
        self._events: list[ChainedDecisionEvent] = []

    @property
    def events(self) -> tuple[ChainedDecisionEvent, ...]:
        return tuple(self._events)

    def append(self, event: DecisionEvent) -> ChainedDecisionEvent:
        if event.case_id != self.case_id:
            raise ValueError("event case_id must match the decision log")
        if event.sequence != len(self._events):
            raise ValueError("event sequence must be the next append-only sequence")
        previous_hash = self._events[-1].event_hash if self._events else None
        chained = ChainedDecisionEvent(
            event=event,
            previous_hash=previous_hash,
            event_hash=_event_hash(event, previous_hash),
        )
        self._events.append(chained)
        return chained

    def verify(self) -> None:
        previous_hash: str | None = None
        for sequence, chained in enumerate(self._events):
            if chained.event.case_id != self.case_id:
                raise ValueError("event case_id changed")
            if chained.event.sequence != sequence:
                raise ValueError("event sequence changed or events were reordered")
            if chained.previous_hash != previous_hash:
                raise ValueError("event chain link changed")
            if chained.event_hash != _event_hash(chained.event, previous_hash):
                raise ValueError("event content or hash changed")
            previous_hash = chained.event_hash

    def project(self) -> DecisionProjection:
        self.verify()
        if not self._events:
            raise ValueError("cannot project an empty decision log")

        approval_id: str | None = None
        execution_status: str | None = None
        unrealized_pnl: Decimal | None = None
        for chained in self._events:
            event = chained.event
            if event.event_type is DecisionEventType.APPROVAL_ISSUED:
                value = event.payload.get("approval_id")
                approval_id = value if isinstance(value, str) else approval_id
            elif event.event_type is DecisionEventType.EXECUTION_UPDATED:
                value = event.payload.get("status")
                execution_status = value if isinstance(value, str) else execution_status
            elif event.event_type is DecisionEventType.PNL_RECORDED:
                value = event.payload.get("unrealized_pnl")
                if isinstance(value, (str, int)):
                    unrealized_pnl = Decimal(value)

        last_event = self._events[-1].event
        return DecisionProjection(
            case_id=self.case_id,
            last_sequence=last_event.sequence,
            last_event_type=last_event.event_type,
            approval_id=approval_id,
            execution_status=execution_status,
            unrealized_pnl=unrealized_pnl,
        )

    def export_decision_card(self) -> DecisionCard:
        self.verify()
        if not self._events:
            raise ValueError("cannot export an empty decision log")
        sanitized_events = tuple(
            chained.event.model_copy(update={"payload": _sanitize(chained.event.payload)})
            for chained in self._events
        )
        return DecisionCard(
            case_id=self.case_id,
            head_hash=self._events[-1].event_hash,
            projection=self.project(),
            events=sanitized_events,
        )

    def to_json(self) -> str:
        self.verify()
        return CHAIN_ADAPTER.dump_json(self.events).decode("utf-8")

    @classmethod
    def from_json(cls, case_id: str, payload: str) -> Self:
        events = CHAIN_ADAPTER.validate_json(payload)
        log = cls(case_id)
        log._events.extend(events)
        log.verify()
        return log


def _event_hash(event: DecisionEvent, previous_hash: str | None) -> str:
    material = f"{previous_hash or 'GENESIS'}|{event.model_dump_json()}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _sanitize(value: JsonValue, key: str | None = None) -> JsonValue:
    if key is not None and (
        "secret" in key.lower() or "api_key" in key.lower() or "account_id" in key.lower()
    ):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {item_key: _sanitize(item_value, item_key) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value
