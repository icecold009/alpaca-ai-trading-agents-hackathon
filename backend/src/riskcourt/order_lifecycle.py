"""Normalize Alpaca order updates into monotonic, reconnect-safe state."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
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

    def to_json(self) -> str:
        """Serialize the normalized state without exposing raw Alpaca payloads."""

        snapshot = self._snapshot
        return json.dumps(
            {
                "client_order_id": snapshot.client_order_id,
                "status": snapshot.status.value,
                "observed_at": snapshot.observed_at.isoformat(),
                "filled_quantity": str(snapshot.filled_quantity),
                "filled_debit": (
                    None if snapshot.filled_debit is None else str(snapshot.filled_debit)
                ),
                "replaced_by": snapshot.replaced_by,
                "connection": snapshot.connection.value,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def from_json(cls, payload: str) -> OrderLifecycleTracker:
        """Restore a previously normalized state and reject malformed payloads."""

        data = json.loads(payload)
        if not isinstance(data, dict):
            raise ValueError("lifecycle state must be a JSON object")
        try:
            observed_at = datetime.fromisoformat(str(data["observed_at"]))
            if observed_at.tzinfo is None or observed_at.utcoffset() is None:
                raise ValueError("lifecycle timestamp must be timezone-aware")
            snapshot = OrderLifecycleSnapshot(
                client_order_id=str(data["client_order_id"]),
                status=ExecutionStatus(str(data["status"])),
                observed_at=observed_at,
                filled_quantity=Decimal(str(data["filled_quantity"])),
                filled_debit=(
                    None if data.get("filled_debit") is None else Decimal(str(data["filled_debit"]))
                ),
                replaced_by=(None if data.get("replaced_by") is None else str(data["replaced_by"])),
                connection=LifecycleConnection(str(data["connection"])),
            )
        except (KeyError, TypeError, ValueError, ArithmeticError) as error:
            raise ValueError("invalid lifecycle state") from error
        if not snapshot.client_order_id:
            raise ValueError("lifecycle client_order_id cannot be empty")
        tracker = object.__new__(cls)
        tracker._snapshot = snapshot
        return tracker

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


class PersistentOrderLifecycle:
    """Persist one normalized order lifecycle atomically across restarts."""

    def __init__(self, path: Path, *, order: Any | None = None) -> None:
        self.path = path
        if path.exists():
            self._tracker = OrderLifecycleTracker.from_json(path.read_text(encoding="utf-8"))
        else:
            if order is None:
                raise ValueError("an initial order is required when lifecycle state is absent")
            self._tracker = OrderLifecycleTracker(order)
            self._write()

    @property
    def snapshot(self) -> OrderLifecycleSnapshot:
        return self._tracker.snapshot

    def apply(self, order: Any) -> OrderLifecycleSnapshot:
        snapshot = self._tracker.apply(order)
        self._write()
        return snapshot

    def mark_disconnected(self, observed_at: datetime) -> OrderLifecycleSnapshot:
        snapshot = self._tracker.mark_disconnected(observed_at)
        self._write()
        return snapshot

    def to_json(self) -> str:
        return self._tracker.to_json()

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            dir=self.path.parent,
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(self._tracker.to_json())
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, self.path)
        finally:
            with suppress(FileNotFoundError):
                os.unlink(temporary_name)


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
