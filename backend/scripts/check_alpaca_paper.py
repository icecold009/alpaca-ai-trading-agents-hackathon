"""Print a sanitized proof of a read-only Alpaca paper-account check."""

from __future__ import annotations

import json

from riskcourt.alpaca_account import AlpacaAccountAdapter
from riskcourt.settings import Settings


def main() -> None:
    state = AlpacaAccountAdapter.from_settings(Settings()).fetch()
    print(json.dumps(state.sanitized_summary(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
