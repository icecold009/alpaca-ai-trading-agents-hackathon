from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from riskcourt.domain import ExecutionStatus
from riskcourt.order_lifecycle import (
    LifecycleConnection,
    OrderLifecycleTracker,
    PersistentOrderLifecycle,
)

NOW = datetime(2026, 8, 30, 15, 0, tzinfo=UTC)


def order(status: str, **kwargs: object) -> SimpleNamespace:
    return SimpleNamespace(
        client_order_id="riskcourt-001",
        status=status,
        submitted_at=NOW,
        updated_at=NOW,
        filled_qty=kwargs.get("filled_qty", "0"),
        filled_avg_price=kwargs.get("filled_avg_price"),
        replaced_by=kwargs.get("replaced_by"),
    )


def test_tracker_maps_submitted_partial_filled_and_preserves_fill_data() -> None:
    tracker = OrderLifecycleTracker(order("new"))
    assert tracker.snapshot.status is ExecutionStatus.SUBMITTED
    assert tracker.apply(order("accepted")).status is ExecutionStatus.ACCEPTED
    assert (
        tracker.apply(
            order("partially_filled", filled_qty="1", filled_avg_price="0.10")
        ).status
        is ExecutionStatus.PARTIALLY_FILLED
    )
    filled = tracker.apply(order("filled", filled_qty="1", filled_avg_price="0.10"))

    assert filled.status is ExecutionStatus.FILLED
    assert filled.filled_quantity == 1
    assert str(filled.filled_debit) == "0.10"


def test_tracker_maps_cancel_reject_and_disconnect_without_losing_state() -> None:
    tracker = OrderLifecycleTracker(order("accepted"))
    canceled = tracker.apply(order("canceled"))
    assert canceled.status is ExecutionStatus.CANCELED
    disconnected = tracker.mark_disconnected(NOW + timedelta(seconds=1))
    assert disconnected.connection is LifecycleConnection.DISCONNECTED
    assert disconnected.status is ExecutionStatus.CANCELED


def test_tracker_rejects_regressions_and_identity_changes() -> None:
    tracker = OrderLifecycleTracker(order("filled"))
    with pytest.raises(ValueError, match="regressed"):
        tracker.apply(order("accepted"))
    changed = order("filled")
    changed.client_order_id = "other"
    with pytest.raises(ValueError, match="client_order_id"):
        tracker.apply(changed)


def test_tracker_round_trips_normalized_state_without_raw_provider_payload() -> None:
    tracker = OrderLifecycleTracker(
        order("partially_filled", filled_qty="1", filled_avg_price="0.10")
    )
    restored = OrderLifecycleTracker.from_json(tracker.to_json())

    assert restored.snapshot == tracker.snapshot
    assert "filled_avg_price" not in restored.to_json()


def test_persistent_lifecycle_recovers_and_records_disconnect(tmp_path: Path) -> None:
    path = tmp_path / "lifecycle.json"
    first = PersistentOrderLifecycle(path, order=order("accepted"))
    first.mark_disconnected(NOW)

    restored = PersistentOrderLifecycle(path)

    assert restored.snapshot.connection is LifecycleConnection.DISCONNECTED
    assert restored.snapshot.status is ExecutionStatus.ACCEPTED
    assert restored.snapshot.client_order_id == "riskcourt-001"
