"""Defined-risk option sizing with no notional or fractional quantity path."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from riskcourt.option_hurdle import VerticalSpreadGeometry
from riskcourt.strategy_math import defined_risk_contracts


class SizingDecision(StrEnum):
    APPROVE = "approve"
    RESIZE = "resize"
    VETO = "veto"


@dataclass(frozen=True, slots=True)
class SizingVerdict:
    decision: SizingDecision
    requested_quantity: int
    approved_quantity: int
    risk_budget: Decimal
    maximum_loss_per_contract: Decimal
    approved_maximum_loss: Decimal
    reason: str


def size_defined_risk_position(
    account_equity: Decimal,
    geometry: VerticalSpreadGeometry,
    requested_quantity: int,
    risk_fraction: Decimal = Decimal("0.005"),
) -> SizingVerdict:
    if type(requested_quantity) is not int or requested_quantity < 1:
        raise ValueError("requested_quantity must be a positive whole number of contracts")

    risk_budget = account_equity * risk_fraction
    affordable_quantity = defined_risk_contracts(
        account_equity=account_equity,
        maximum_loss=geometry.maximum_loss,
        risk_fraction=risk_fraction,
        contract_cap=1,
    )
    if affordable_quantity == 0:
        return SizingVerdict(
            decision=SizingDecision.VETO,
            requested_quantity=requested_quantity,
            approved_quantity=0,
            risk_budget=risk_budget,
            maximum_loss_per_contract=geometry.maximum_loss,
            approved_maximum_loss=Decimal("0"),
            reason="one_contract_exceeds_risk_budget",
        )

    approved_quantity = min(requested_quantity, affordable_quantity)
    decision = (
        SizingDecision.APPROVE if approved_quantity == requested_quantity else SizingDecision.RESIZE
    )
    return SizingVerdict(
        decision=decision,
        requested_quantity=requested_quantity,
        approved_quantity=approved_quantity,
        risk_budget=risk_budget,
        maximum_loss_per_contract=geometry.maximum_loss,
        approved_maximum_loss=geometry.maximum_loss * approved_quantity,
        reason=(
            "within_one_contract_risk_cap"
            if decision is SizingDecision.APPROVE
            else "resized_to_one_contract_mvp_cap"
        ),
    )
