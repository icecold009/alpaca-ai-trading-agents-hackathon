"""Fail-closed Alpaca multi-leg paper-order mapping and submission gate."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol, cast

from alpaca.common.exceptions import APIError
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderClass, PositionIntent, TimeInForce
from alpaca.trading.requests import LimitOrderRequest, OptionLegRequest

from riskcourt.approval_guard import IdempotencyRegistry, SubmissionAction
from riskcourt.settings import RuntimeMode, Settings
from riskcourt.spread_selector import SpreadCandidate


def client_order_id_for_approval(approval_id: str) -> str:
    """Create a stable, bounded broker ID for one immutable approval."""

    if not approval_id or len(approval_id) > 120:
        raise ValueError("approval_id must contain 1 to 120 characters")
    digest = hashlib.sha256(approval_id.encode("utf-8")).hexdigest()
    return f"rc_{digest[:45]}"


def request_fingerprint(request: LimitOrderRequest) -> str:
    """Hash the canonical order fields so retries cannot mutate the approved order."""

    canonical = json.dumps(
        request.model_dump(mode="json", exclude_none=True),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class OrderSubmitClient(Protocol):
    def submit_order(self, order_data: LimitOrderRequest) -> Any: ...

    def get_order_by_client_id(self, client_id: str) -> Any: ...


class SubmissionOutcomeUnknown(RuntimeError):
    """The request may have reached Alpaca, but its result could not be confirmed."""


class SubmissionRejected(RuntimeError):
    """Alpaca definitively rejected the request and no matching order exists."""


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
            ),
            registry=IdempotencyRegistry(settings.riskcourt_state_dir / "idempotency.json"),
        )

    @staticmethod
    def build_vertical_order(
        candidate: SpreadCandidate,
        *,
        client_order_id: str,
        quantity: int = 1,
        limit_price: Decimal | None = None,
    ) -> LimitOrderRequest:
        if not client_order_id or len(client_order_id) > 48:
            raise ValueError("client_order_id must contain 1 to 48 characters")
        geometry = candidate.geometry
        debit = geometry.net_debit if limit_price is None else limit_price
        if debit <= 0 or debit > geometry.spread_width:
            raise ValueError("limit price must be a positive debit no greater than spread width")
        if quantity < 1:
            raise ValueError("quantity must be positive")
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
            qty=quantity,
            order_class=OrderClass.MLEG,
            legs=legs,
            limit_price=float(debit),
            time_in_force=TimeInForce.DAY,
            client_order_id=client_order_id,
        )

    @staticmethod
    def build_vertical_exit_order(
        candidate: SpreadCandidate,
        *,
        client_order_id: str,
        credit_price: Decimal,
        quantity: int = 1,
    ) -> LimitOrderRequest:
        """Build a closing credit order; execution remains approval-gated."""

        if not client_order_id or len(client_order_id) > 48:
            raise ValueError("client_order_id must contain 1 to 48 characters")
        if credit_price <= 0 or credit_price > candidate.geometry.spread_width:
            raise ValueError("exit credit must be positive and no greater than spread width")
        if quantity < 1:
            raise ValueError("quantity must be positive")
        return LimitOrderRequest(
            qty=quantity,
            order_class=OrderClass.MLEG,
            legs=[
                OptionLegRequest(
                    symbol=candidate.long_contract.occ_symbol,
                    ratio_qty=1,
                    position_intent=PositionIntent.SELL_TO_CLOSE,
                ),
                OptionLegRequest(
                    symbol=candidate.short_contract.occ_symbol,
                    ratio_qty=1,
                    position_intent=PositionIntent.BUY_TO_CLOSE,
                ),
            ],
            limit_price=-float(credit_price),
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
        if action is SubmissionAction.REJECT:
            raise ValueError("client_order_id is already bound to a different request")
        if action is SubmissionAction.REPLAY:
            try:
                existing = self.lookup_order_by_client_id(client_order_id)
            except Exception as error:
                raise SubmissionOutcomeUnknown(
                    "order lookup failed; submission outcome remains unknown"
                ) from error
            if existing is not None:
                return SubmissionResult(action, request_hash, existing)

        try:
            response = self._client.submit_order(request)
        except Exception as error:
            try:
                existing = self.lookup_order_by_client_id(client_order_id)
            except Exception as lookup_error:
                raise SubmissionOutcomeUnknown(
                    "submission and order lookup failed; outcome remains unknown"
                ) from lookup_error
            if existing is not None:
                return SubmissionResult(SubmissionAction.REPLAY, request_hash, existing)
            if _is_definitive_rejection(error):
                raise SubmissionRejected("Alpaca rejected the paper order") from error
            raise SubmissionOutcomeUnknown(
                "submission outcome could not be confirmed; retry to reconcile"
            ) from error
        return SubmissionResult(action, request_hash, response)

    def lookup_order_by_client_id(self, client_order_id: str) -> Any | None:
        """Find an existing broker order; only an explicit 404 means not found."""

        try:
            return self._client.get_order_by_client_id(client_order_id)
        except APIError as error:
            if error.status_code == 404:
                return None
            raise


def _is_definitive_rejection(error: Exception) -> bool:
    if not isinstance(error, APIError):
        return False
    status_code = error.status_code
    return status_code is not None and 400 <= status_code < 500 and status_code not in {
        408,
        409,
        422,
        429,
    }
