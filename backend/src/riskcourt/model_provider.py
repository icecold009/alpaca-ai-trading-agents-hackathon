"""Credential-optional structured model provider boundary."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from threading import Thread
from typing import Protocol, TypeVar

from pydantic import Field, JsonValue, ValidationError

from riskcourt.domain import ContractModel, Identifier


class ProviderUnavailable(RuntimeError):
    pass


class ProviderRequest(ContractModel):
    request_id: Identifier
    prompt_version: str = Field(min_length=1, max_length=120)
    model_version: str = Field(min_length=1, max_length=120)
    payload: dict[str, JsonValue]
    repair: bool = False


@dataclass(frozen=True, slots=True)
class ProviderReply:
    output: dict[str, JsonValue]
    cost_units: Decimal = Decimal("0")


class ProviderClient(Protocol):
    def complete(self, request: ProviderRequest) -> ProviderReply: ...


@dataclass(frozen=True, slots=True)
class ProviderTrace:
    request_id: str
    prompt_version: str
    model_version: str
    attempts: int
    cost_units: Decimal


T = TypeVar("T", bound=ContractModel)


@dataclass(frozen=True, slots=True)
class ProviderResult[T]:
    data: T
    trace: ProviderTrace


class ProviderBoundary:
    def __init__(
        self,
        client: ProviderClient,
        *,
        timeout_seconds: float = 10.0,
        max_calls: int = 3,
        max_cost_units: Decimal = Decimal("3"),
    ) -> None:
        if timeout_seconds <= 0 or max_calls < 1 or max_cost_units < 0:
            raise ValueError("provider limits must be positive and ordered")
        self._client = client
        self._timeout_seconds = timeout_seconds
        self._max_calls = max_calls
        self._max_cost_units = max_cost_units
        self._calls = 0
        self._cost = Decimal("0")

    def call(self, request: ProviderRequest, response_model: type[T]) -> ProviderResult[T]:
        attempts = 0
        total_cost = Decimal("0")
        current = request
        while attempts < 2:
            attempts += 1
            reply = self._invoke(current)
            total_cost += reply.cost_units
            try:
                data = response_model.model_validate(reply.output)
            except ValidationError as error:
                if attempts == 2:
                    raise ProviderUnavailable(
                        "provider returned invalid structured output"
                    ) from error
                current = request.model_copy(update={"repair": True})
                continue
            return ProviderResult(
                data=data,
                trace=ProviderTrace(
                    request_id=request.request_id,
                    prompt_version=request.prompt_version,
                    model_version=request.model_version,
                    attempts=attempts,
                    cost_units=total_cost,
                ),
            )
        raise AssertionError("provider call loop must return or raise")

    def _invoke(self, request: ProviderRequest) -> ProviderReply:
        if self._calls >= self._max_calls:
            raise ProviderUnavailable("provider call cap exceeded")
        self._calls += 1
        result: list[ProviderReply] = []
        failure: list[BaseException] = []

        def run() -> None:
            try:
                reply = self._client.complete(request)
                if reply.cost_units < 0:
                    raise ProviderUnavailable("provider reported negative cost")
                if self._cost + reply.cost_units > self._max_cost_units:
                    raise ProviderUnavailable("provider cost cap exceeded")
                result.append(reply)
                self._cost += reply.cost_units
            except BaseException as error:  # pragma: no cover - re-raised below
                failure.append(error)

        worker = Thread(target=run, daemon=True)
        worker.start()
        worker.join(self._timeout_seconds)
        if worker.is_alive():
            raise ProviderUnavailable("provider request timed out")
        if failure:
            error = failure[0]
            if isinstance(error, ProviderUnavailable):
                raise error
            raise ProviderUnavailable("provider request failed") from error
        if not result:
            raise ProviderUnavailable("provider returned no response")
        return result[0]
