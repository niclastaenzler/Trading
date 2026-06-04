"""Tradable market universe, grouped by asset class.

Symbols use Capital.com-style epic codes where possible. On the paper/synthetic
path any symbol works; for live Capital.com a few epics may differ per account —
the user can adjust the list in Configuration.
"""

from __future__ import annotations

UNIVERSE: dict[str, list[str]] = {
    "forex": [
        "EURUSD", "GBPUSD", "USDJPY", "AUDUSD",
        "USDCAD", "USDCHF", "NZDUSD", "EURGBP", "EURJPY",
    ],
    "commodities": [
        # Metals
        "GOLD", "SILVER", "PLATINUM", "PALLADIUM", "COPPER",
        "ALUMINIUM", "ZINC", "NICKEL", "LEAD",
        # Energy
        "OIL_CRUDE", "OIL_BRENT", "NATURALGAS", "GASOLINE", "HEATINGOIL",
        # Agriculture / softs
        "WHEAT", "CORN", "SOYBEAN", "COFFEE", "SUGAR", "COCOA",
        "COTTON", "ORANGEJUICE",
    ],
    "indices": [
        "US500", "US100", "US30", "GER40", "UK100",
    ],
    "stocks": [
        "AAPL", "TSLA", "AMZN", "MSFT", "NVDA", "GOOGL", "META",
    ],
}


def all_symbols() -> list[str]:
    out: list[str] = []
    for group in UNIVERSE.values():
        out.extend(group)
    return out


def symbols_for(asset_classes: list[str]) -> list[str]:
    out: list[str] = []
    for ac in asset_classes:
        out.extend(UNIVERSE.get(ac, []))
    return out
