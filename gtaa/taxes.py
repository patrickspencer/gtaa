"""After-tax returns of a monthly-rebalanced portfolio in a US taxable account.

The backtest reports pre-tax returns. This module re-runs a set of monthly
weights as an actual portfolio of tax lots and pays the taxes a US
individual would owe, at a chosen federal bracket, to give an after-tax
growth rate. It is deliberately a simplified model of the tax code, but
the parts that matter for a monthly rotation strategy are all here:

* **Lots and holding periods.** Every purchase is a lot. Sales consume lots
  first-in-first-out. A gain on a lot held more than a year is long-term;
  otherwise short-term, taxed as ordinary income. A monthly strategy that
  keeps re-selecting the same asset keeps its old lots, so its gains are
  not automatically short-term; a strategy that rotates realises them.
* **Distributions.** Each month's total return is split into price return
  and distributions using the fund's actual cash dividends. Distributions
  are taxed in the year received (as qualified dividends for stock funds,
  as ordinary income for bond and REIT funds) and reinvested as a new lot.
* **Special assets.** Gold held through GLD is a collectible: long-term
  gains are taxed at the ordinary rate capped at 28%. DBC holds futures
  contracts and issues a K-1: its gains are marked to market every year
  whether sold or not, 60% long-term and 40% short-term.
* **Year-end.** Gains and losses are netted, a net loss carries forward
  to later years, and the year's tax is paid out of the portfolio by
  selling a little of everything (which itself realises a small gain the
  following year).
* **Liquidation.** The "if liquidated" figure also pays the tax that would
  be due on selling everything at the end, so nothing is left deferred.

Simplifications, all of which understate the tax somewhat: no state tax
unless a rate is given (and then it is applied to Treasury interest too);
no wash-sale rule; no $3,000 ordinary-income offset for net losses; all
stock-fund dividends treated as qualified (a share of foreign funds' are
not); no foreign tax credit; no 20% deduction on REIT distributions; the
NIIT is applied to the whole bracket rather than above a threshold.

At 0% rates the simulation reproduces the pre-tax equity curve exactly,
which is how it is tested.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import duckdb
import pandas as pd

LONG_TERM_DAYS = 365          # held for *more* than a year
FUTURES_LONG_SHARE = 0.60     # Section 1256: 60% long-term, 40% short-term


@dataclass(frozen=True)
class Bracket:
    name: str
    ordinary: float       # federal rate on ordinary income and short-term gains
    long_term: float      # federal rate on long-term gains and qualified dividends
    niit: float = 0.0     # net investment income tax, where it applies
    state: float = 0.0

    def rate(self, kind: str) -> float:
        base = {"short": self.ordinary, "ordinary": self.ordinary,
                "long": self.long_term, "qualified": self.long_term,
                "collectible": min(self.ordinary, 0.28)}[kind]
        return base + self.niit + self.state

    def with_state(self, state: float) -> "Bracket":
        return Bracket(self.name, self.ordinary, self.long_term, self.niit, state)


# 2025 federal brackets for ordinary income and long-term gains. The 3.8%
# net investment income tax starts at $200k (single) / $250k (joint) of
# income, which is inside the 32% bracket for most filers.
BRACKETS = (
    Bracket("12% / 0%", 0.12, 0.00),
    Bracket("22% / 15%", 0.22, 0.15),
    Bracket("24% / 15%", 0.24, 0.15),
    Bracket("32% / 15% + NIIT", 0.32, 0.15, 0.038),
    Bracket("35% / 15% + NIIT", 0.35, 0.15, 0.038),
    Bracket("37% / 20% + NIIT", 0.37, 0.20, 0.038),
)
NO_TAX = Bracket("pre-tax", 0.0, 0.0)

MONTHLY_SQL = """
WITH daily AS (
    SELECT symbol, date, adj_close, dividend,
           lag(close) OVER (PARTITION BY symbol ORDER BY date) AS prev_close,
           date_trunc('month', date) AS month
    FROM prices
    WHERE symbol IN (SELECT UNNEST(?::VARCHAR[]))
)
SELECT symbol, month,
       arg_max(adj_close, date) AS adj_close,
       -- Growth from reinvesting the month's distributions, matching how the
       -- adjusted close folds them in: 1 / prod(1 - dividend / previous close).
       exp(-sum(CASE WHEN prev_close > 0 AND dividend > 0
                     THEN ln(1 - dividend / prev_close) ELSE 0 END)) - 1 AS distribution
FROM daily
GROUP BY symbol, month
ORDER BY symbol, month
"""


def monthly_inputs(con: duckdb.DuckDBPyConnection, symbols) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per symbol and month: the price-only return and the distribution
    yield, which compound to the total return of the adjusted close."""
    df = con.execute(MONTHLY_SQL, [list(symbols)]).df()
    df["month"] = pd.to_datetime(df["month"])
    closes = df.pivot(index="month", columns="symbol", values="adj_close").sort_index()
    dist = df.pivot(index="month", columns="symbol", values="distribution").sort_index()
    total = closes.pct_change()
    price = (1.0 + total) / (1.0 + dist) - 1.0
    return price, dist


@dataclass
class Lot:
    symbol: str
    acquired: pd.Timestamp
    units: float
    cost: float


@dataclass
class Portfolio:
    """Lots held in units of a per-symbol price index that starts at 1."""
    symbols: list[str]
    price: dict[str, float] = field(default_factory=dict)
    lots: dict[str, list[Lot]] = field(default_factory=dict)

    def __post_init__(self):
        self.price = {s: 1.0 for s in self.symbols}
        self.lots = {s: [] for s in self.symbols}

    def value(self, symbol: str) -> float:
        return sum(l.units for l in self.lots[symbol]) * self.price[symbol]

    def total(self) -> float:
        return sum(self.value(s) for s in self.symbols)

    def buy(self, symbol: str, amount: float, date: pd.Timestamp) -> None:
        if amount > 0:
            self.lots[symbol].append(Lot(symbol, date, amount / self.price[symbol], amount))

    def sell(self, symbol: str, amount: float, date: pd.Timestamp) -> list[tuple[float, int]]:
        """Sell `amount` of value, oldest lots first. Returns (gain, days held)."""
        gains, remaining, price = [], amount, self.price[symbol]
        lots = self.lots[symbol]
        while remaining > 1e-12 and lots:
            lot = lots[0]
            lot_value = lot.units * price
            take = min(lot_value, remaining)
            share = take / lot_value
            gains.append((take - lot.cost * share, (date - lot.acquired).days))
            lot.units -= lot.units * share
            lot.cost -= lot.cost * share
            remaining -= take
            if lot.units <= 1e-12:
                lots.pop(0)
        return gains

    def sell_fraction(self, fraction: float, date: pd.Timestamp) -> list[tuple[str, float, int]]:
        """Sell the same fraction of every lot (how a tax bill is paid)."""
        out = []
        for s in self.symbols:
            for lot in self.lots[s]:
                take = lot.units * fraction
                out.append((s, take * self.price[s] - lot.cost * fraction, (date - lot.acquired).days))
                lot.units -= take
                lot.cost -= lot.cost * fraction
        return out

    def mark_to_market(self, symbol: str) -> float:
        """Realise the unrealised gain on a symbol and reset its cost basis."""
        gain = 0.0
        for lot in self.lots[symbol]:
            value = lot.units * self.price[symbol]
            gain += value - lot.cost
            lot.cost = value
        return gain


def classify(gain: float, days: int, treatment: str) -> dict[str, float]:
    """Split one realised gain into the buckets it is taxed in."""
    if treatment == "futures":
        return {"long": gain * FUTURES_LONG_SHARE, "short": gain * (1 - FUTURES_LONG_SHARE)}
    if days > LONG_TERM_DAYS:
        return {"collectible" if treatment == "collectible" else "long": gain}
    return {"short": gain}


def settle(buckets: dict[str, float], carry: float, bracket: Bracket) -> tuple[float, float]:
    """The year's tax and the loss carried forward.

    Losses offset gains: short-term against short-term first, then the rest
    against the other buckets (28% collectible gains before 15/20% long-term
    ones, as the code allows). What is left of a net loss carries forward.
    """
    short, long_, coll = buckets.get("short", 0.0), buckets.get("long", 0.0), buckets.get("collectible", 0.0)
    loss = carry + max(0.0, -short) + max(0.0, -long_) + max(0.0, -coll)
    short, long_, coll = max(short, 0.0), max(long_, 0.0), max(coll, 0.0)
    for name in ("short", "collectible", "long"):
        gain = {"short": short, "collectible": coll, "long": long_}[name]
        used = min(gain, loss)
        loss -= used
        if name == "short":
            short -= used
        elif name == "collectible":
            coll -= used
        else:
            long_ -= used
    tax = (short * bracket.rate("short") + long_ * bracket.rate("long") + coll * bracket.rate("collectible")
           + buckets.get("ordinary", 0.0) * bracket.rate("ordinary")
           + buckets.get("qualified", 0.0) * bracket.rate("qualified"))
    return tax, loss


@dataclass
class TaxResult:
    bracket: Bracket
    months: int
    final_value: float           # after paying each year's tax, open gains untaxed
    liquidation_value: float     # after also paying tax on open gains at the end
    income: dict[str, float]     # taxable amounts by bucket over the whole run
    tax_paid: float

    def cagr(self, liquidated: bool = False) -> float:
        v = self.liquidation_value if liquidated else self.final_value
        return v ** (12.0 / self.months) - 1.0


def simulate(
    weights: pd.DataFrame,
    price: pd.DataFrame,
    distribution: pd.DataFrame,
    treatment: dict[str, str],
    bracket: Bracket,
) -> TaxResult:
    """Run `weights` (decided at each month-end, indexed by month) as a
    taxable portfolio through the months that follow each decision."""
    symbols = list(weights.columns)
    months = list(weights.index)
    port = Portfolio(symbols)
    buckets: dict[str, float] = defaultdict(float)
    income: dict[str, float] = defaultdict(float)
    carry, tax_paid = 0.0, 0.0

    def month_end(m):
        return m + pd.offsets.MonthEnd(0)

    def realise(symbol, gain, days):
        for kind, amount in classify(gain, days, treatment[symbol]).items():
            buckets[kind] += amount

    def year_end(date, last):
        nonlocal carry, tax_paid
        for s in symbols:
            if treatment[s] == "futures":
                realise(s, port.mark_to_market(s), 0)
        for k, v in buckets.items():
            income[k] += v
        tax, carry = settle(buckets, carry, bracket)
        buckets.clear()
        if tax > 0:
            for s, gain, days in port.sell_fraction(tax / port.total(), date):
                realise(s, gain, days)
        tax_paid += tax

    for s, w in weights.iloc[0].items():
        port.buy(s, float(w), month_end(months[0]))
    realised_months = [price.index[price.index.get_loc(m) + 1] for m in months]  # the month after each decision
    for i, t in enumerate(realised_months):
        date = month_end(t)
        for s in symbols:
            port.price[s] *= 1.0 + float(price.loc[t, s])
            d = float(distribution.loc[t, s])
            if d > 0 and port.lots[s]:
                cash = port.value(s) * d
                buckets["ordinary" if treatment[s] in ("bond", "reit", "futures") else "qualified"] += cash
                port.buy(s, cash, date)
        if t in weights.index:
            total = port.total()
            targets = {s: float(weights.loc[t, s]) * total for s in symbols}
            for s in symbols:                       # sells first, then buys with the proceeds
                excess = port.value(s) - targets[s]
                if excess > 1e-12:
                    for gain, days in port.sell(s, excess, date):
                        realise(s, gain, days)
            for s in symbols:
                shortfall = targets[s] - port.value(s)
                if shortfall > 1e-12:
                    port.buy(s, shortfall, date)
        last = i == len(realised_months) - 1
        if date.month == 12 or last:
            year_end(date, last)

    final_value = port.total()
    end = month_end(realised_months[-1])
    for s in symbols:
        for gain, days in port.sell(s, port.value(s), end):
            realise(s, gain, days)
    for k, v in buckets.items():
        income[k] += v
    tax, _ = settle(buckets, carry, bracket)
    return TaxResult(bracket, len(realised_months), final_value, final_value - tax, dict(income), tax_paid + tax)


def after_tax_table(weights, price, distribution, treatment, brackets=BRACKETS, state=0.0) -> list[TaxResult]:
    return [simulate(weights, price, distribution, treatment, b.with_state(state)) for b in brackets]
