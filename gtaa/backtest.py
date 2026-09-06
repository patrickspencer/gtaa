"""Monthly backtest of the GTAA selection rule.

The engine is deliberately simple, following Faber's stated assumptions:

* Decisions are made on the last trading day of each month, using only
  data up to that close, and applied for the following month.
* Every held asset gets an equal 1/top_n share; every slot whose asset failed
  the trend filter earns the cash return instead. The portfolio is rebalanced
  back to those weights every month.
* Returns are total returns (adjusted closes), so dividends are reinvested.
* No transaction costs, slippage, or taxes.

The backtest starts at the first month-end where every asset in the
universe has a score (i.e. 12 months of history) and the cash proxy has
prices; anything earlier would rank an incomplete universe.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb
import pandas as pd

from . import metrics
from .signals import compute_signals, full_universe_months, month_is_complete, select
from .universe import CASH, SYMBOLS


@dataclass
class BacktestResult:
    top_n: int
    equity: pd.Series            # portfolio value, 1.0 at start, indexed by month-end
    returns: pd.Series           # monthly portfolio returns
    weights: pd.DataFrame        # weight per symbol (plus 'CASH') decided each month-end
    benchmark: pd.Series         # equal-weight buy-and-hold of the same universe
    summary: dict


def monthly_returns(con: duckdb.DuckDBPyConnection, symbols) -> pd.DataFrame:
    """Month-end to month-end total returns, one column per symbol.

    A trailing partial month (prices that stop before the month's last
    weekday) is dropped: it is not a month-end return yet.
    """
    df = con.execute(
        """
        WITH month_ends AS (
            SELECT symbol, date, adj_close, date_trunc('month', date) AS month,
                   row_number() OVER (PARTITION BY symbol, date_trunc('month', date)
                                      ORDER BY date DESC) AS rn
            FROM prices
            WHERE symbol IN (SELECT UNNEST(?::VARCHAR[]))
        )
        SELECT symbol, month, date AS month_end, adj_close
        FROM month_ends WHERE rn = 1 ORDER BY symbol, month
        """,
        [list(symbols)],
    ).df()
    df["month"] = pd.to_datetime(df["month"])
    df["month_end"] = pd.to_datetime(df["month_end"])
    latest = df["month"] == df["month"].max()
    complete = month_is_complete(df["month_end"], ~latest)
    df = df[complete]
    closes = df.pivot(index="month", columns="symbol", values="adj_close").sort_index()
    return closes.pct_change()


def run_backtest(
    con: duckdb.DuckDBPyConnection,
    top_n: int,
    start: str | None = None,
    end: str | None = None,
    symbols=SYMBOLS,
) -> BacktestResult:
    signals = select(compute_signals(con, symbols), top_n)
    rets = monthly_returns(con, list(symbols) + [CASH.symbol])

    # Weights decided at month m apply to the returns realised in month m+1.
    w = signals.pivot(index="month", columns="symbol", values="weight").fillna(0.0)
    w = w.reindex(columns=list(symbols), fill_value=0.0)
    w["CASH"] = 1.0 - w.sum(axis=1)

    eligible = full_universe_months(signals, expected=len(symbols))
    first = eligible.min()
    if start:
        first = max(first, pd.Timestamp(start))
    w = w[w.index >= first]
    if end:
        w = w[w.index <= pd.Timestamp(end)]

    realised = rets.shift(-1).reindex(w.index)  # next month's returns, aligned to decision month
    realised = realised.rename(columns={CASH.symbol: "CASH"})
    realised = realised.reindex(columns=w.columns)
    # The last decision has no realised month yet.
    valid = realised.notna().all(axis=1)
    w, realised = w[valid], realised[valid]

    port = (w * realised).sum(axis=1)
    # Index the results by the month-end the return was realised at.
    realised_index = rets.index[rets.index.get_indexer(port.index) + 1]
    port.index = realised_index
    equity = (1.0 + port).cumprod()
    equity.loc[w.index[0]] = 1.0
    equity = equity.sort_index()

    bench_rets = rets.loc[realised_index, list(symbols)].mean(axis=1)
    benchmark = (1.0 + bench_rets).cumprod()
    benchmark.loc[w.index[0]] = 1.0
    benchmark = benchmark.sort_index()

    cash_rets = rets.loc[realised_index, CASH.symbol]
    summary = {
        "start": equity.index[0].strftime("%Y-%m"),
        "end": equity.index[-1].strftime("%Y-%m"),
        "months": len(port),
        **metrics.summarise(port, cash_rets),
        "avg_cash_weight": float(w["CASH"].mean()),
        "equal_weight": metrics.summarise(bench_rets, cash_rets),
    }
    return BacktestResult(top_n, equity, port, w, benchmark, summary)
