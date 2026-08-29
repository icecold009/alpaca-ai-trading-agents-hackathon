"""Print sanitized provenance for a live read-only SPY market-data check."""

import json

from riskcourt.alpaca_market_data import AlpacaUnderlyingAdapter
from riskcourt.settings import Settings


def main() -> None:
    state = AlpacaUnderlyingAdapter.from_settings(Settings()).fetch()
    print(json.dumps(state.sanitized_summary(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
