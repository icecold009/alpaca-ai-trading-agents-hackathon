"""Print sanitized proof of a bounded live SPY option-chain read."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from riskcourt.alpaca_option_chain import AlpacaOptionChainAdapter
from riskcourt.settings import Settings


def main() -> None:
    today = datetime.now(UTC).date()
    state = AlpacaOptionChainAdapter.from_settings(Settings()).fetch(
        "SPY",
        expiration_from=today + timedelta(days=7),
        expiration_to=today + timedelta(days=21),
        strike_from=Decimal("500"),
        strike_to=Decimal("800"),
    )
    print(json.dumps(state.sanitized_summary(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
