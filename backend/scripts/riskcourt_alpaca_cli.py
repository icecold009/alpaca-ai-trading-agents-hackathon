"""RiskCourt's sanitized Alpaca integration CLI boundary.

This wrapper deliberately exposes only read capabilities. It is not a replacement
for the official Alpaca MCP/CLI requirement; it makes that missing dependency
explicit instead of granting execution to research tooling.
"""

from __future__ import annotations

import argparse
import json

from riskcourt.alpaca_account import AlpacaAccountAdapter
from riskcourt.alpaca_cli import capability_inventory
from riskcourt.alpaca_market_data import AlpacaUnderlyingAdapter
from riskcourt.settings import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description="RiskCourt Alpaca integration doctor")
    parser.add_argument("command", choices=("doctor", "read-only", "dry-run"))
    args = parser.parse_args()

    if args.command == "doctor":
        settings = Settings()
        print(
            json.dumps(
                {
                    "mode": settings.riskcourt_mode.value,
                    "official_alpaca_cli": False,
                    "official_alpaca_mcp": False,
                    "capabilities": capability_inventory(),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    if args.command == "dry-run":
        print(json.dumps({"execution_enabled": False, "reason": "read-only integration boundary"}))
        return

    settings = Settings()
    account = AlpacaAccountAdapter.from_settings(settings).fetch()
    market = AlpacaUnderlyingAdapter.from_settings(settings).fetch()
    print(
        json.dumps(
            {"account": account.sanitized_summary(), "market": market.sanitized_summary()}
        )
    )


if __name__ == "__main__":
    main()
