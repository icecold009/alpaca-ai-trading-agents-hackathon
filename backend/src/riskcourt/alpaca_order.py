"""Fail-closed Alpaca multi-leg paper-order mapping and submission gate."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol, cast

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderClass, PositionIntent, TimeInForce
from alpaca.trading.requests import LimitOrderRequest, OptionLegRequest

from riskcourt.approval_guard import IdempotencyRegistry, SubmissionAction
from riskcourt.settings import RuntimeMode, Settings
from riskcourt.spread_selector import SpreadCandidate


class OrderSubmitClient(Protocol):
    def submit_order(self, order_data: LimitOrderRequest) -> Any: ...


@dataclass(frozen=True, slots=True)
class SubmissionResult:
    action: SubmissionAction
    request_sha256: str
    response: Any | None = None


class AlpacaOrderAdapter:
    def __init__(
        self,
        client: OrderSubmitClient,
        registry: IdempotencyRegistry | None = None,
    ) -> None:
        self._client = client
        self._registry = registry or IdempotencyRegistry()

    @classmethod
    def from_settings(cls, settings: Settings) -> AlpacaOrderAdapter:
        if settings.riskcourt_mode is not RuntimeMode.PAPER:
            raise ValueError("Alpaca order submission requires paper mode")
        assert settings.alpaca_api_key_id is not None
        assert settings.alpaca_api_secret_key is not None
        return cls(
            cast(
                OrderSubmitClient,
                TradingClient(
                    api_key=settings.alpaca_api_key_id.get_secret_value(),
                    secret_key=settings.alpaca_api_secret_key.get_secret_value(),
                    paper=True,
                    url_override=str(settings.alpaca_paper_base_url).rstrip("/"),
                ),
            )
        )

    @staticmethod
    def build_vertical_order(
        candidate: SpreadCandidate,
        *,
        client_order_id: str,
        limit_price: Decimal | None = None,
    ) -> LimitOrderRequest:
        if not client_order_id or len(client_order_id) > 48:
            raise ValueError("client_order_id must contain 1 to 48 characters")
        geometry = candidate.geometry
        debit = geometry.net_debit if limit_price is None else limit_price
        if debit <= 0 or debit > geometry.spread_width:
            raise ValueError("limit price must be a positive debit no greater than spread width")
        legs = [
            OptionLegRequest(
                symbol=candidate.long_contract.occ_symbol,
                ratio_qty=1,
                position_intent=PositionIntent.BUY_TO_OPEN,
            ),
            OptionLegRequest(
                symbol=candidate.short_contract.occ_symbol,
                ratio_qty=1,
                position_intent=PositionIntent.SELL_TO_OPEN,
            ),
        ]
        return LimitOrderRequest(
            qty=1,
            order_class=OrderClass.MLEG,
            legs=legs,
            limit_price=float(debit),
            time_in_force=TimeInForce.DAY,
            client_order_id=client_order_id,
        )

    def submit(self, request: LimitOrderRequest, *, approved: bool = False) -> SubmissionResult:
        """Submit only an approved request, reserving its client ID idempotently."""

        if not approved:
            raise PermissionError("paper order requires an explicit approval")
        request_hash = hashlib.sha256(request.model_dump_json().encode()).hexdigest()
        client_order_id = request.client_order_id
        if not client_order_id:
            raise ValueError("request must include a client_order_id")
        action = self._registry.reserve(client_order_id, request_hash)
        if action is SubmissionAction.SUBMIT:
            return SubmissionResult(action, request_hash, self._client.submit_order(request))
        return SubmissionResult(action, request_hash)
