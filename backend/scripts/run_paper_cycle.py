"""Run one explicit, fail-closed RiskCourt Alpaca paper cycle.

The default command is a read-only preflight.  Submission requires both
``--submit`` and a private ``module:attribute`` provider, plus an explicit
daily-P&L value.  Output is sanitized for evidence capture.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from riskcourt.alpaca_account import AlpacaAccountAdapter
from riskcourt.alpaca_market_data import AlpacaUnderlyingAdapter, MarketDataUnavailable
from riskcourt.alpaca_option_chain import AlpacaOptionChainAdapter, OptionChainUnavailable
from riskcourt.alpaca_order import AlpacaOrderAdapter
from riskcourt.event_store import PersistentDecisionLog
from riskcourt.model_provider import ProviderBoundary
from riskcourt.order_lifecycle import PersistentOrderLifecycle
from riskcourt.paper_loop import PaperCycleDependencies, run_paper_cycle
from riskcourt.paper_runner import build_risk_state, load_provider_client, sanitize_result
from riskcourt.settings import RuntimeMode, Settings


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        settings = Settings()
        if settings.riskcourt_mode is not RuntimeMode.PAPER:
            raise ValueError("RISKCOURT_MODE=paper is required; recorded mode is read-only")
        daily_pnl = _parse_decimal(args.daily_pnl, "--daily-pnl", required=args.submit)
        case_id = args.case_id or _default_case_id()
        if args.submit:
            if args.provider is None:
                raise ValueError("--submit requires --provider module:attribute")
            result, log, lifecycle_persisted = _submit(settings, args, case_id, daily_pnl)
            output: dict[str, Any] = sanitize_result(result)
            output["audit"] = {
                "event_count": len(log.events),
                "chain_verified": _verify_log(log),
            }
            output["lifecycle_persisted"] = lifecycle_persisted
            print(json.dumps(output, indent=2, sort_keys=True))
            return 0
        output = _preflight(settings, args.symbol, case_id)
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0
    except (ValueError, InvalidOperation, ImportError, AttributeError, TypeError) as error:
        print(json.dumps({"status": "error", "reason": _safe_reason(error)}, sort_keys=True))
        return 2
    except (MarketDataUnavailable, OptionChainUnavailable, OSError, RuntimeError):
        print(
            json.dumps(
                {"status": "error", "reason": "paper_provider_unavailable"}, sort_keys=True
            )
        )
        return 2
    except Exception:
        # Do not leak SDK payloads, URLs, identifiers, or provider tracebacks.
        print(json.dumps({"status": "error", "reason": "paper_cycle_failed"}, sort_keys=True))
        return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", help="stable lowercase case identifier for audit persistence")
    parser.add_argument("--symbol", default="SPY", help="underlying ticker (release scope: SPY)")
    parser.add_argument("--daily-pnl", help="known paper daily P&L used by the drawdown gate")
    parser.add_argument("--provider", help="private provider module:attribute factory")
    parser.add_argument("--minimum-edge", default="0.08", help="jury edge required after hurdle")
    parser.add_argument(
        "--submit",
        action="store_true",
        help="submit exactly one approved one-contract paper order; default is read-only",
    )
    return parser


def _preflight(settings: Settings, symbol: str, case_id: str) -> dict[str, object]:
    account = AlpacaAccountAdapter.from_settings(settings).fetch()
    now = account.clock.timestamp
    market = AlpacaUnderlyingAdapter.from_settings(settings).fetch(symbol=symbol, now=now)
    chain = AlpacaOptionChainAdapter.from_settings(settings).fetch(
        symbol,
        expiration_from=now.date(),
        expiration_to=now.date() + timedelta(days=21),
        strike_from=Decimal("1"),
        strike_to=Decimal("1000"),
    )
    return {
        "status": "preflight_ok",
        "case_id": case_id,
        "submission_enabled": False,
        "account": account.sanitized_summary(),
        "market": market.sanitized_summary(),
        "chain": chain.sanitized_summary(),
    }


def _submit(
    settings: Settings,
    args: argparse.Namespace,
    case_id: str,
    daily_pnl: Decimal,
) -> tuple[Any, PersistentDecisionLog, bool]:
    provider = ProviderBoundary(load_provider_client(args.provider))
    account_adapter = AlpacaAccountAdapter.from_settings(settings)
    account = account_adapter.fetch()
    risk = build_risk_state(account, daily_pnl=daily_pnl)
    event_path = settings.riskcourt_state_dir / "events" / f"{case_id}.json"
    if event_path.exists():
        raise ValueError("case-id already has a persisted audit log; choose a new case-id")
    log = PersistentDecisionLog(case_id, event_path)
    deps = PaperCycleDependencies(
        account=account_adapter,
        market=AlpacaUnderlyingAdapter.from_settings(settings),
        chain=AlpacaOptionChainAdapter.from_settings(settings),
        orders=AlpacaOrderAdapter.from_settings(settings),
        provider=provider,
        risk=risk,
        event_log=log,
    )
    result = run_paper_cycle(
        deps,
        case_id=case_id,
        symbol=args.symbol,
        minimum_edge=_parse_decimal(args.minimum_edge, "--minimum-edge", required=True),
    )
    lifecycle_persisted = False
    response = result.submission.response if result.submission is not None else None
    if response is not None:
        lifecycle_path = settings.riskcourt_state_dir / "lifecycle" / f"{case_id}.json"
        if lifecycle_path.exists():
            raise ValueError("case-id already has persisted lifecycle state")
        PersistentOrderLifecycle(lifecycle_path, order=response)
        lifecycle_persisted = True
    return result, log, lifecycle_persisted


def _parse_decimal(value: str | None, flag: str, *, required: bool) -> Decimal:
    if value is None:
        if required:
            raise ValueError(f"{flag} is required for paper submission")
        return Decimal("0")
    parsed = Decimal(value)
    if not parsed.is_finite():
        raise ValueError(f"{flag} must be a finite decimal")
    return parsed


def _default_case_id() -> str:
    return "case_runner_" + datetime.now(UTC).strftime("%Y%m%d_%H%M%S")


def _verify_log(log: PersistentDecisionLog) -> bool:
    log.verify()
    return True


def _safe_reason(error: BaseException) -> str:
    message = str(error).lower()
    if "provider" in message:
        return "provider_configuration_invalid"
    if "paper" in message or "alpaca" in message or "credential" in message:
        return "paper_configuration_invalid"
    return "invalid_paper_cycle_request"


if __name__ == "__main__":
    raise SystemExit(main())
