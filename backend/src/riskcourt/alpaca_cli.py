"""Sanitized capability inventory for the RiskCourt Alpaca boundary."""


def capability_inventory() -> dict[str, bool]:
    """Keep order mutation outside all research/read capabilities."""

    return {
        "account.read": True,
        "market_data.read": True,
        "option_chain.read": True,
        "orders.submit": False,
        "orders.cancel": False,
    }
