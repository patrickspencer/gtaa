"""The GTAA rules, as one SQL query over month-end prices.

For every symbol and month this computes:

* the month-end adjusted close (last trading day of the month);
* the 1-, 3-, 6- and 12-month total returns from month-end closes;
* the momentum score: the plain average of those four returns;
* the 10-month simple moving average of month-end closes, and whether the
  current close is above it;
* the rank of the score within the month across the universe.

The selection rule is then: take the `top_n` highest scores; each of those
is held for the coming month if it closed above its 10-month average,
otherwise that slot sits in cash. Assets outside the top `top_n` are never
held, even if they are above their average. Everything is decided on the
month-end close and applied for the following month.

Rows are only produced once a symbol has a full 12 months of history and
ten month-ends for the average, so nothing is ever computed on a partial
window.
"""

from __future__ import annotations

import pandas as pd
import duckdb

from .universe import LOOKBACKS, SMA_MONTHS, SYMBOLS

SIGNALS_SQL = f"""
WITH month_ends AS (
    -- The last trading day of each calendar month, per symbol.
    SELECT symbol, date, adj_close,
           date_trunc('month', date) AS month,
           row_number() OVER (PARTITION BY symbol, date_trunc('month', date)
                              ORDER BY date DESC) AS rn
    FROM prices
    WHERE symbol IN (SELECT UNNEST(?::VARCHAR[]))
),
monthly AS (
    SELECT symbol, month, date AS month_end, adj_close
    FROM month_ends
    WHERE rn = 1
),
features AS (
    SELECT symbol, month, month_end, adj_close,
           -- Returns are only valid if the lagged row really is k months
           -- earlier; a gap in the data would otherwise mislabel it.
           CASE WHEN lag(month, 1)  OVER w = month - INTERVAL 1 MONTH
                THEN adj_close / lag(adj_close, 1)  OVER w - 1 END AS r1,
           CASE WHEN lag(month, 3)  OVER w = month - INTERVAL 3 MONTH
                THEN adj_close / lag(adj_close, 3)  OVER w - 1 END AS r3,
           CASE WHEN lag(month, 6)  OVER w = month - INTERVAL 6 MONTH
                THEN adj_close / lag(adj_close, 6)  OVER w - 1 END AS r6,
           CASE WHEN lag(month, 12) OVER w = month - INTERVAL 12 MONTH
                THEN adj_close / lag(adj_close, 12) OVER w - 1 END AS r12,
           CASE WHEN lag(month, {SMA_MONTHS - 1}) OVER w = month - INTERVAL {SMA_MONTHS - 1} MONTH
                THEN avg(adj_close) OVER (PARTITION BY symbol ORDER BY month
                                          ROWS BETWEEN {SMA_MONTHS - 1} PRECEDING AND CURRENT ROW)
           END AS sma,
           lead(month, 1) OVER w IS NOT NULL AS month_complete
    FROM monthly
    WINDOW w AS (PARTITION BY symbol ORDER BY month)
),
scored AS (
    SELECT *,
           (r1 + r3 + r6 + r12) / 4.0 AS score,
           adj_close > sma AS above_sma
    FROM features
    WHERE r1 IS NOT NULL AND r3 IS NOT NULL AND r6 IS NOT NULL AND r12 IS NOT NULL
      AND sma IS NOT NULL
),
ranked AS (
    SELECT *,
           row_number() OVER (PARTITION BY month ORDER BY score DESC, symbol) AS rank,
           count(*)     OVER (PARTITION BY month) AS universe_size
    FROM scored
)
SELECT symbol, month, month_end, adj_close, r1, r3, r6, r12, score, sma, above_sma,
       rank, universe_size, month_complete
FROM ranked
ORDER BY month, rank
"""

assert LOOKBACKS == (1, 3, 6, 12), "SIGNALS_SQL is written for the 1/3/6/12-month score"


def month_is_complete(month_end: pd.Series, has_later_month: pd.Series) -> pd.Series:
    """A month is complete once a later month exists, or when its last price
    falls on the month's last weekday (so a month-end run counts as final)."""
    last_weekday = month_end + pd.offsets.BMonthEnd(0)
    return has_later_month | (month_end >= last_weekday)


def compute_signals(con: duckdb.DuckDBPyConnection, symbols=SYMBOLS) -> pd.DataFrame:
    """Every symbol's score, rank and trend status for every month-end."""
    df = con.execute(SIGNALS_SQL, [list(symbols)]).df()
    df["month"] = pd.to_datetime(df["month"])
    df["month_end"] = pd.to_datetime(df["month_end"])
    df["month_complete"] = month_is_complete(df["month_end"], df["month_complete"].astype(bool))
    return df


def select(signals: pd.DataFrame, top_n: int) -> pd.DataFrame:
    """Apply the selection rule and assign weights.

    Adds `selected` (in the top_n by score), `held` (selected and above the
    average) and `weight` (1/top_n if held, else 0). The cash weight for a
    month is 1 - sum(weight).
    """
    out = signals.copy()
    out["selected"] = out["rank"] <= top_n
    out["held"] = out["selected"] & out["above_sma"]
    out["weight"] = out["held"].astype(float) / top_n
    return out


def allocation(signals: pd.DataFrame, top_n: int, month=None) -> pd.DataFrame:
    """The portfolio decided at one month-end (default: the latest complete
    month), one row per slot, including the cash slot."""
    sel = select(signals, top_n)
    if month is None:
        complete = sel[sel["month_complete"]]
        month = (complete if not complete.empty else sel)["month"].max()
    rows = sel[(sel["month"] == month) & sel["selected"]].sort_values("rank")
    cash = 1.0 - rows["weight"].sum()
    return rows, cash, month


def full_universe_months(signals: pd.DataFrame, expected: int = len(SYMBOLS)) -> pd.Series:
    """Months where every symbol in the universe had a score."""
    counts = signals.groupby("month")["symbol"].nunique()
    return counts[counts == expected].index.to_series()
