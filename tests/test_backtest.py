"""The backtest arithmetic, checked against returns worked out by hand."""

from __future__ import annotations

import duckdb
import pandas as pd
import pytest

from gtaa import data
from gtaa.backtest import run_backtest
from gtaa.metrics import cagr, max_drawdown

from test_signals import load


@pytest.fixture
def con():
    c = duckdb.connect(":memory:")
    c.execute(data.SCHEMA)
    return c


def geometric(start, monthly_rate, n):
    return [start * (1 + monthly_rate) ** i for i in range(n)]


def test_portfolio_return_is_the_weighted_next_month_return(con):
    # Two assets, both trending up so both are always held; cash flat.
    a = geometric(100, 0.02, 16)   # +2% a month
    b = geometric(100, 0.01, 16)   # +1% a month
    load(con, {"A": a, "B": b, "BIL": [100.0] * 16})
    r = run_backtest(con, top_n=2, symbols=("A", "B"))
    # Each month the portfolio earns the average of 2% and 1%.
    assert r.returns.iloc[0] == pytest.approx(0.015)
    assert (r.returns.round(12) == 0.015).all()
    assert r.equity.iloc[0] == 1.0
    assert r.equity.iloc[-1] == pytest.approx(1.015 ** len(r.returns))


def test_cash_slot_earns_the_cash_return(con):
    a = geometric(100, 0.02, 16)
    # B collapses in month 13 and stays below its average: its slot is cash.
    b = geometric(100, 0.05, 13) + [20.0, 20.0, 20.0]
    bil = geometric(100, 0.004, 16)  # T-bills 0.4% a month
    load(con, {"A": a, "B": b, "BIL": bil})
    r = run_backtest(con, top_n=2, symbols=("A", "B"))
    last = r.returns.iloc[-1]
    assert r.weights.iloc[-1]["B"] == 0.0
    assert r.weights.iloc[-1]["CASH"] == 0.5
    assert last == pytest.approx(0.5 * 0.02 + 0.5 * 0.004)


def test_decisions_use_only_information_available_at_month_end(con):
    # A is flat for 13 months then jumps 50% in month 14. The decision made
    # at month 13 cannot know about the jump, so with B strictly better
    # through month 13, B is held and A is not, and the jump is not earned
    # by an A position decided in advance of it.
    a = [100.0] * 14 + [150.0, 150.0]
    b = geometric(100, 0.01, 16)
    load(con, {"A": a, "B": b, "BIL": [100.0] * 16})
    r = run_backtest(con, top_n=1, symbols=("A", "B"))
    decision_month = pd.Timestamp("2021-01-01")   # 13th month-end (Jan 2021)
    assert r.weights.loc[decision_month, "A"] == 0.0
    assert r.weights.loc[decision_month, "B"] == 1.0


def test_backtest_starts_when_every_asset_has_a_score(con):
    # B has two fewer months of history than A: the first eligible decision
    # is the first month where B also has 12 months behind it.
    a = geometric(100, 0.01, 18)
    b = geometric(100, 0.01, 16)
    load(con, {"A": a, "BIL": [100.0] * 18})
    load(con, {"B": b}, start="2020-03-31")
    r = run_backtest(con, top_n=2, symbols=("A", "B"))
    assert r.weights.index[0] == pd.Timestamp("2021-03-01")


def test_metrics_on_a_known_series():
    monthly = pd.Series([0.01] * 12)
    assert cagr(monthly) == pytest.approx(1.01 ** 12 - 1)
    dd = pd.Series([0.10, -0.50, 0.20])
    assert max_drawdown(dd) == pytest.approx(-0.5)


def test_a_trailing_partial_month_is_not_a_realised_return(con):
    a = geometric(100, 0.01, 16)
    b = geometric(100, 0.02, 16)
    load(con, {"A": a, "B": b, "BIL": [100.0] * 16})
    before = run_backtest(con, top_n=2, symbols=("A", "B"))
    # A few days into the next month, prices exist but the month is not over.
    con.executemany("INSERT INTO prices (symbol, date, close, adj_close) VALUES (?, ?, ?, ?)",
                    [(s, "2021-05-04", 999.0, 999.0) for s in ("A", "B", "BIL")])
    after = run_backtest(con, top_n=2, symbols=("A", "B"))
    assert list(after.returns.index) == list(before.returns.index)
    assert after.equity.iloc[-1] == pytest.approx(before.equity.iloc[-1])
