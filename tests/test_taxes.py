"""The after-tax engine, on portfolios whose tax bills can be worked out by hand."""

from __future__ import annotations

import duckdb
import pandas as pd
import pytest

from gtaa import data
from gtaa.backtest import run_backtest
from gtaa.taxes import NO_TAX, Bracket, monthly_inputs, settle, simulate
from gtaa.universe import CASH

from test_signals import load

TOP = Bracket("top", 0.40, 0.20)


def frame(values, symbols, start="2019-12-01"):
    idx = pd.date_range(start, periods=len(values), freq="MS")
    return pd.DataFrame({s: values for s in symbols}, index=idx)


def weights(rows, symbols, start="2019-12-01"):
    idx = pd.date_range(start, periods=len(rows), freq="MS")
    return pd.DataFrame(rows, index=idx, columns=symbols)


def test_buy_and_hold_pays_nothing_until_liquidation():
    # 24 decisions holding A at +1% a month, no distributions. Decisions start
    # in December so realised months are whole calendar years.
    w = weights([[1.0]] * 24, ["A"])
    price = frame([0.01] * 25, ["A"])
    dist = frame([0.0] * 25, ["A"])
    r = simulate(w, price, dist, {"A": "equity"}, TOP)
    assert r.final_value == pytest.approx(1.01 ** 24)
    assert r.tax_paid == pytest.approx((1.01 ** 24 - 1) * 0.20)   # 24 months > a year: long-term
    assert r.liquidation_value == pytest.approx(1.01 ** 24 - (1.01 ** 24 - 1) * 0.20)
    assert r.cagr() == pytest.approx(1.01 ** 12 - 1)


def test_a_rotation_realises_short_term_gains_every_year():
    # Alternate between A and B each month; both rise 1% a month.
    rows = [[1.0, 0.0] if i % 2 == 0 else [0.0, 1.0] for i in range(12)]
    w = weights(rows, ["A", "B"])
    price = frame([0.01] * 13, ["A", "B"])
    dist = frame([0.0] * 13, ["A", "B"])
    r = simulate(w, price, dist, {"A": "equity", "B": "equity"}, TOP)
    # Every month's 1% gain is realised at the next rebalance. Eleven months
    # are realised by year-end and taxed at 40% out of the portfolio; the
    # December gain is still open until liquidation.
    gain = 1.01 ** 12 - 1
    assert r.income["short"] == pytest.approx(gain)
    assert r.income.get("long", 0.0) == 0.0
    assert r.final_value == pytest.approx(1.01 ** 12 - (1.01 ** 11 - 1) * 0.40)
    assert r.liquidation_value == pytest.approx(1.01 ** 12 - gain * 0.40)


def test_distributions_are_taxed_when_received_and_reinvested():
    # No price change; a 1% distribution each month for one year.
    w = weights([[1.0]] * 12, ["A"])
    price = frame([0.0] * 13, ["A"])
    dist = frame([0.01] * 13, ["A"])
    bond = simulate(w, price, dist, {"A": "bond"}, TOP)
    equity = simulate(w, price, dist, {"A": "equity"}, TOP)
    total = 1.01 ** 12 - 1
    assert bond.income["ordinary"] == pytest.approx(total)
    assert bond.final_value == pytest.approx(1.01 ** 12 - total * 0.40)
    assert equity.income["qualified"] == pytest.approx(total)
    assert equity.final_value == pytest.approx(1.01 ** 12 - total * 0.20)
    # Reinvested distributions raised the cost basis: nothing more is due on liquidation.
    assert bond.liquidation_value == pytest.approx(bond.final_value)


def test_losses_carry_forward_against_later_gains():
    assert settle({"short": -0.10}, 0.0, TOP) == (0.0, pytest.approx(0.10))
    tax, carry = settle({"short": 0.05, "long": 0.10}, 0.10, TOP)
    # The 0.10 loss wipes the short-term gain first, then half the long-term gain.
    assert tax == pytest.approx(0.05 * 0.20) and carry == 0.0
    tax, carry = settle({"short": 0.02, "ordinary": 0.03}, 0.0, TOP)
    assert tax == pytest.approx(0.05 * 0.40)


def test_futures_are_marked_to_market_sixty_forty():
    w = weights([[1.0]] * 12, ["D"])
    price = frame([0.01] * 13, ["D"])
    dist = frame([0.0] * 13, ["D"])
    r = simulate(w, price, dist, {"D": "futures"}, TOP)
    gain = 1.01 ** 12 - 1
    assert r.income["long"] == pytest.approx(0.6 * gain)
    assert r.income["short"] == pytest.approx(0.4 * gain)
    assert r.final_value == pytest.approx(1.01 ** 12 - gain * (0.6 * 0.20 + 0.4 * 0.40))
    assert r.liquidation_value == pytest.approx(r.final_value)   # nothing left unrealised


def test_collectible_long_term_rate_is_capped_at_28_percent():
    w = weights([[1.0]] * 24, ["G"])
    price = frame([0.01] * 25, ["G"])
    dist = frame([0.0] * 25, ["G"])
    r = simulate(w, price, dist, {"G": "collectible"}, TOP)
    gain = 1.01 ** 24 - 1
    assert r.tax_paid == pytest.approx(gain * 0.28)
    low = simulate(w, price, dist, {"G": "collectible"}, Bracket("low", 0.12, 0.0))
    assert low.tax_paid == pytest.approx(gain * 0.12)


def test_zero_rates_reproduce_the_backtest_exactly():
    con = duckdb.connect(":memory:")
    con.execute(data.SCHEMA)
    a = [100 * 1.02 ** i for i in range(20)]
    b = [100 * 1.05 ** i for i in range(14)] + [20.0] * 6      # collapses, so its slot goes to cash
    load(con, {"A": a, "B": b, CASH.symbol: [100 * 1.001 ** i for i in range(20)]})
    con.execute("UPDATE prices SET dividend = 0.5 WHERE symbol = 'A' AND date >= '2020-06-01'")
    result = run_backtest(con, top_n=2, symbols=("A", "B"))
    w = result.weights.rename(columns={"CASH": CASH.symbol})
    price, dist = monthly_inputs(con, list(w.columns))
    r = simulate(w, price, dist, {"A": "equity", "B": "equity", CASH.symbol: "bond"}, NO_TAX)
    assert r.final_value == pytest.approx(result.equity.iloc[-1])
    assert r.liquidation_value == pytest.approx(result.equity.iloc[-1])
    assert r.tax_paid == 0.0
