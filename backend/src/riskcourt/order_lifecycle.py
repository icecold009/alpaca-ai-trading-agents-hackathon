"""Normalize Alpaca order updates into monotonic, reconnect-safe state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from riskcourt.domain import ExecutionStatus


class LifecycleConnection(Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"


@dataclass(frozen=True, slots=True)
class OrderLifecycleSnapshot:
    client_order_id: str
    status: ExecutionStatus
    observed_at: datetime
    filled_quantity: Decimal
    filled_debit: Decimal | None
    replaced_by: str | None
    connection: LifecycleConnection


class OrderLifecycleTracker:
    """Apply polling or websocket updates without allowing terminal regressions."""

    def __init__(self, order: Any) -> None:
        self._snapshot = self._translate(order, LifecycleConnection.CONNECTED)

    @property
    def snapshot(self) -> OrderLifecycleSnapshot:
        return self._snapshot

    def apply(self, order: Any) -> OrderLifecycleSnapshot:
        update = self._translate(order, LifecycleConnection.CONNECTED)
        if update.client_order_id != self._snapshot.client_order_id:
            raise ValueError("order update client_order_id changed")
        if _rank(update.status) < _rank(self._snapshot.status):
            raise ValueError("order update regressed lifecycle state")
        self._snapshot = update
        return update

    def mark_disconnected(self, observed_at: datetime) -> OrderLifecycleSnapshot:
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("disconnect timestamp must be timezone-aware")
        self._snapshot = OrderLifecycleSnapshot(
            client_order_id=self._snapshot.client_order_id,
            status=self._snapshot.status,
            observed_at=observed_at,
            filled_quantity=self._snapshot.filled_quantity,
            filled_debit=self._snapshot.filled_debit,
            replaced_by=self._snapshot.replaced_by,
            connection=LifecycleConnection.DISCONNECTED,
        )
        return self._snapshot

    @staticmethod
    def _translate(order: Any, connection: LifecycleConnection) -> OrderLifecycleSnapshot:
        observed_at = getattr(order, "updated_at", None) or getattr(order, "submitted_at", None)
        if not isinstance(observed_at, datetime) or observed_at.tzinfo is None:
            raise ValueError("order timestamp must be timezone-aware")
        status = _status(getattr(order, "status", None))
        filled_quantity = Decimal(str(getattr(order, "filled_qty", None) or "0"))
        filled_price = getattr(order, "filled_avg_price", None)
        return OrderLifecycleSnapshot(
            client_order_id=str(order.client_order_id),
            status=status,
            observed_at=observed_at,
            filled_quantity=filled_quantity,
            filled_debit=None if filled_price is None else Decimal(str(filled_price)),
            replaced_by=(None if order.replaced_by is None else str(order.replaced_by)),
            connection=connection,
        )


def _status(value: Any) -> ExecutionStatus:
    raw = getattr(value, "value", value)
    if raw in {"new", "pending_new"}:
        return ExecutionStatus.SUBMITTED
    if raw in {"accepted", "accepted_for_bidding", "held", "calculated"}:
        return ExecutionStatus.ACCEPTED
    if raw == "partially_filled":
        return ExecutionStatus.PARTIALLY_FILLED
    if raw == "filled":
        return ExecutionStatus.FILLED
    if raw in {"canceled", "expired", "done_for_day", "pending_cancel"}:
        return ExecutionStatus.CANCELED
    if raw in {"rejected", "stopped", "suspended"}:
        return ExecutionStatus.REJECTED
    raise ValueError(f"unsupported Alpaca order status: {raw}")


def _rank(status: ExecutionStatus) -> int:
    return {
        ExecutionStatus.SUBMITTED: 0,
        ExecutionStatus.ACCEPTED: 1,
        ExecutionStatus.PARTIALLY_FILLED: 2,
        ExecutionStatus.FILLED: 3,
        ExecutionStatus.CANCELED: 3,
        ExecutionStatus.REJECTED: 3,
    }[status]
