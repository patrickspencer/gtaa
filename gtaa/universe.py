"""The GTAA 13 asset classes and the ETFs that stand in for them.

Faber's papers rank thirteen asset classes; this module names each one, the
ETF used as its proxy, and the reasoning. The README discusses the choices
at length. Keep this file as the single source of truth for the universe.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Asset:
    asset_class: str
    symbol: str
    name: str
    inception: str  # first full month of usable price history, YYYY-MM
    tax: str        # how a US taxable account is taxed on it; see gtaa/taxes.py


# Order matters only for display. Symbols must be unique. The last field is
# the tax treatment: "equity" (qualified dividends), "bond" and "reit"
# (distributions are ordinary income), "collectible" (GLD: long-term gains
# capped at 28%), "futures" (DBC: gains marked to market yearly, 60% long-term).
ASSETS: tuple[Asset, ...] = (
    Asset("US large-cap value", "VTV", "Vanguard Value ETF", "2004-02", "equity"),
    Asset("US large-cap momentum", "MTUM", "iShares MSCI USA Momentum Factor ETF", "2013-05", "equity"),
    Asset("US small-cap value", "VBR", "Vanguard Small-Cap Value ETF", "2004-02", "equity"),
    Asset("US small-cap", "VB", "Vanguard Small-Cap ETF", "2004-02", "equity"),
    Asset("Foreign developed equities", "VEA", "Vanguard FTSE Developed Markets ETF", "2007-08", "equity"),
    Asset("Emerging-market equities", "VWO", "Vanguard FTSE Emerging Markets ETF", "2005-04", "equity"),
    Asset("US intermediate Treasuries", "IEF", "iShares 7-10 Year Treasury Bond ETF", "2002-08", "bond"),
    Asset("US long-term Treasuries", "TLT", "iShares 20+ Year Treasury Bond ETF", "2002-08", "bond"),
    Asset("Foreign government bonds", "BWX", "SPDR Bloomberg International Treasury Bond ETF", "2007-11", "bond"),
    Asset("US corporate bonds", "LQD", "iShares iBoxx $ Investment Grade Corporate Bond ETF", "2002-08", "bond"),
    Asset("Commodities", "DBC", "Invesco DB Commodity Index Tracking Fund", "2006-03", "futures"),
    Asset("Gold", "GLD", "SPDR Gold Shares", "2004-12", "collectible"),
    Asset("Real estate", "VNQ", "Vanguard Real Estate ETF", "2004-10", "reit"),
)

CASH = Asset("Cash (90-day T-bills)", "BIL", "SPDR Bloomberg 1-3 Month T-Bill ETF", "2007-06", "bond")

SYMBOLS: tuple[str, ...] = tuple(a.symbol for a in ASSETS)
ALL_SYMBOLS: tuple[str, ...] = SYMBOLS + (CASH.symbol,)

# Momentum lookbacks, in months, whose returns are averaged into the score.
LOOKBACKS: tuple[int, ...] = (1, 3, 6, 12)

# Trend filter: an asset is held only if its month-end close is above the
# simple average of its last SMA_MONTHS month-end closes.
SMA_MONTHS = 10


def asset(symbol: str) -> Asset:
    for a in ASSETS:
        if a.symbol == symbol:
            return a
    if symbol == CASH.symbol:
        return CASH
    raise KeyError(symbol)
