from datetime import UTC, datetime
from decimal import Decimal

import pytest

from riskcourt.pnl import create_pnl_snapshot


def test_snapshot_records_profit_and_loss_from_position_value() -> None:
    snapshot = create_pnl_snapshot(
        snapshot_id="pnl_001",
        case_id="case_edge_positive",
        execution_id="execution_001",
        observed_at=datetime(2026, 8, 30, tzinfo=UTC),
        position_value=Decimal("180"),
        cost_basis=Decimal("120"),
        realized_pnl=Decimal("0"),
        maximum_loss=Decimal("120"),
        evidence_ids=("account_001",),
    )

    assert snapshot.unrealized_pnl == Decimal("60")
    assert snapshot.realized_pnl == Decimal("0")


def test_snapshot_rejects_negative_values_and_zero_risk() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        create_pnl_snapshot(
            snapshot_id="pnl_001",
            case_id="case_edge_positive",
            execution_id="execution_001",
            observed_at=datetime(2026, 8, 30, tzinfo=UTC),
            position_value=Decimal("-1"),
            cost_basis=Decimal("1"),
            realized_pnl=Decimal("0"),
            maximum_loss=Decimal("1"),
            evidence_ids=("account_001",),
        )
    with pytest.raises(ValueError, match="positive"):
        create_pnl_snapshot(
            snapshot_id="pnl_001",
            case_id="case_edge_positive",
            execution_id="execution_001",
            observed_at=datetime(2026, 8, 30, tzinfo=UTC),
            position_value=Decimal("0"),
            cost_basis=Decimal("1"),
            realized_pnl=Decimal("0"),
            maximum_loss=Decimal("0"),
            evidence_ids=("account_001",),
        )
