from riskcourt.alpaca_cli import capability_inventory


def test_cli_inventory_keeps_execution_outside_read_tools() -> None:
    inventory = capability_inventory()

    assert inventory["account.read"] is True
    assert inventory["market_data.read"] is True
    assert inventory["option_chain.read"] is True
    assert inventory["orders.submit"] is False
    assert inventory["orders.cancel"] is False
