"""Immutable paper P&L snapshots derived from execution and position reads."""

from datetime import datetime
from decimal import Decimal

from riskcourt.domain import PnLSnapshot


def create_pnl_snapshot(
    *,
    snapshot_id: str,
    case_id: str,
    execution_id: str,
    observed_at: datetime,
    position_value: Decimal,
    cost_basis: Decimal,
    realized_pnl: Decimal,
    maximum_loss: Decimal,
    evidence_ids: tuple[str, ...],
) -> PnLSnapshot:
    """Record unrealized P&L as current position value less strategy cost."""

    if position_value < 0 or cost_basis < 0:
        raise ValueError("position value and cost basis cannot be negative")
    if maximum_loss <= 0:
        raise ValueError("maximum loss must be positive")
    return PnLSnapshot(
        snapshot_id=snapshot_id,
        case_id=case_id,
        execution_id=execution_id,
        observed_at=observed_at,
        position_value=position_value,
        cost_basis=cost_basis,
        unrealized_pnl=position_value - cost_basis,
        realized_pnl=realized_pnl,
        maximum_loss=maximum_loss,
        evidence_ids=evidence_ids,
    )
