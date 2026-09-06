"""The selection rules, checked on hand-built price paths."""

from __future__ import annotations

import duckdb
import pandas as pd
import pytest

from gtaa import data
from gtaa.signals import allocation, compute_signals, select


def month_ends(n: int, start: str = "2020-01-31") -> list[pd.Timestamp]:
    return list(pd.date_range(start, periods=n, freq="ME"))


def load(con: duckdb.DuckDBPyConnection, series: dict[str, list[float]], start="2020-01-31"):
    """Store one price per month-end (plus a mid-month price, to prove the
    month-end pick is the last trading day)."""
    rows = []
    for symbol, closes in series.items():
        for me, close in zip(month_ends(len(closes), start), closes):
            mid = me - pd.Timedelta(days=15)
            rows.append((symbol, mid.date().isoformat(), close * 0.5, close * 0.5))  # ignored
            rows.append((symbol, me.date().isoformat(), close, close))
    con.executemany("INSERT INTO prices (symbol, date, close, adj_close) VALUES (?, ?, ?, ?)", rows)


@pytest.fixture
def con():
    c = duckdb.connect(":memory:")
    c.execute(data.SCHEMA)
    return c


def flat(v=100.0, n=14):
    return [v] * n


def test_score_is_the_average_of_1_3_6_12_month_returns(con):
    # A series that doubles every month makes each k-month return 2^k - 1.
    prices = [2.0 ** i for i in range(14)]
    load(con, {"A": prices})
    s = compute_signals(con, ["A"])
    last = s.iloc[-1]
    expected = ((2 - 1) + (8 - 1) + (64 - 1) + (4096 - 1)) / 4
    assert last["r1"] == pytest.approx(1.0)
    assert last["r12"] == pytest.approx(4095.0)
    assert last["score"] == pytest.approx(expected)


def test_no_signal_until_twelve_months_of_history(con):
    load(con, {"A": flat(n=14)})
    s = compute_signals(con, ["A"])
    # 14 month-ends: signals only from the 13th (12 prior months needed).
    assert len(s) == 2
    assert s["month"].min() == pd.Timestamp("2021-01-01")


def test_uses_the_last_trading_day_of_the_month(con):
    load(con, {"A": flat(n=14)})  # load() also stores a mid-month price at half value
    s = compute_signals(con, ["A"])
    assert (s["adj_close"] == 100.0).all()


def test_sma_filter_sends_a_falling_asset_to_cash(con):
    rising = [100 + i for i in range(14)]
    # Strong momentum over 12 months but a sharp fall in the last month, so
    # the close drops below the 10-month average.
    crashed = [100 + 10 * i for i in range(13)] + [60.0]
    load(con, {"UP": rising, "DOWN": crashed})
    s = select(compute_signals(con, ["UP", "DOWN"]), top_n=2)
    last = s[s["month"] == s["month"].max()].set_index("symbol")
    assert bool(last.loc["UP", "above_sma"]) is True
    assert bool(last.loc["DOWN", "above_sma"]) is False
    assert last.loc["UP", "weight"] == 0.5
    assert last.loc["DOWN", "weight"] == 0.0        # its slot is cash, not re-filled


def test_only_the_top_n_are_held_even_if_others_are_trending(con):
    series = {f"S{i}": [100 * (1 + 0.01 * i) ** m for m in range(14)] for i in range(1, 5)}
    load(con, series)
    s = select(compute_signals(con, series.keys()), top_n=2)
    last = s[s["month"] == s["month"].max()].set_index("symbol")
    assert list(last.sort_values("rank").index[:2]) == ["S4", "S3"]
    assert last.loc["S4", "weight"] == 0.5 and last.loc["S3", "weight"] == 0.5
    assert last.loc["S2", "weight"] == 0.0 and last.loc["S1", "weight"] == 0.0
    assert bool(last.loc["S2", "above_sma"]) is True   # trending, but not top-2


def test_allocation_reports_cash_for_empty_slots(con):
    # DOWN collapses in month 13; month 14 exists so that month 13 is the
    # latest *complete* month, which is the one allocation() reports.
    load(con, {"UP": [100 + i for i in range(14)],
               "DOWN": [100 + 10 * i for i in range(12)] + [60.0, 60.0]})
    rows, cash, month = allocation(compute_signals(con, ["UP", "DOWN"]), top_n=2)
    assert month == pd.Timestamp("2021-01-01")
    assert cash == pytest.approx(0.5)
    assert set(rows["symbol"]) == {"UP", "DOWN"}


def test_a_gap_in_history_invalidates_the_lookback(con):
    load(con, {"A": flat(n=20)})   # Jan 2020 .. Aug 2021
    con.execute("DELETE FROM prices WHERE symbol = 'A' AND date BETWEEN '2020-06-01' AND '2020-06-30'")
    s = compute_signals(con, ["A"])
    # A month-end only gets a signal once its 12-month lookback no longer
    # spans the missing June: the first such month is July 2021.
    assert list(s["month"]) == [pd.Timestamp("2021-07-01"), pd.Timestamp("2021-08-01")]


def test_latest_month_is_flagged_provisional(con):
    load(con, {"A": flat(n=14)})
    s = compute_signals(con, ["A"])
    assert bool(s.iloc[-1]["month_complete"]) is False
    assert bool(s.iloc[-2]["month_complete"]) is True
