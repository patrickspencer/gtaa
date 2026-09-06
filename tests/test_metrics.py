"""Rolling windows and drawdown episodes, on series whose answers are known."""

import pandas as pd
import pytest

from gtaa.metrics import drawdowns, rolling_returns, rolling_summary, underwater_summary


def monthly(values, start="2020-01-01"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="MS"), dtype=float)


def test_rolling_return_is_the_annualised_window_growth():
    r = monthly([0.01] * 12 + [0.02] * 12)
    twelve = rolling_returns(r, 12)
    assert len(twelve) == 13
    assert twelve.iloc[0] == pytest.approx(1.01 ** 12 - 1)     # the first 12 months
    assert twelve.iloc[-1] == pytest.approx(1.02 ** 12 - 1)    # the last 12 months
    # A 24-month window annualises the geometric mean of the two halves.
    assert rolling_returns(r, 24).iloc[0] == pytest.approx((1.01 ** 12 * 1.02 ** 12) ** 0.5 - 1)


def test_rolling_summary_names_the_extreme_windows():
    # Flat, then a bad year, then flat again.
    r = monthly([0.0] * 12 + [-0.05] * 12 + [0.0] * 12)
    s = rolling_summary(r, windows=(12,))[0]
    assert s["months"] == 12 and s["windows"] == 25
    assert s["worst"] == pytest.approx(0.95 ** 12 - 1)
    assert s["worst_span"] == ("2021-01", "2021-12")
    assert s["best"] == pytest.approx(0.0)
    assert s["best_span"] == ("2020-01", "2020-12")
    assert s["positive"] == 0.0


def test_drawdown_episodes_are_delimited_by_the_peaks():
    # Up, then a 20% fall over two months, recovery, then an unrecovered 10% fall.
    r = monthly([0.10, -0.10, -1 / 9, 0.25, 0.10, -0.10, 0.0])
    dd = drawdowns(r)
    assert len(dd) == 2
    first = dd.iloc[0]        # deepest first
    assert first["depth"] == pytest.approx(-0.2)
    assert first["peak"] == pd.Timestamp("2020-01-01")
    assert first["trough"] == pd.Timestamp("2020-03-01")
    assert first["recovery"] == pd.Timestamp("2020-04-01")
    assert first["months_to_trough"] == 2 and first["months_to_recover"] == 1 and first["months"] == 3
    second = dd.iloc[1]
    assert second["depth"] == pytest.approx(-0.1)
    assert pd.isna(second["recovery"]) and pd.isna(second["months_to_recover"])
    assert second["months"] == 2     # June and July, still underwater


def test_underwater_summary_counts_months_below_the_peak():
    r = monthly([0.10, -0.10, -1 / 9, 0.25, 0.10, -0.10, 0.0])
    u = underwater_summary(r)
    assert u["time_underwater"] == pytest.approx(4 / 7)   # Feb, Mar, Jun, Jul
    assert u["longest_months"] == 3
    assert u["longest_span"][0] == pd.Timestamp("2020-01-01")
    assert u["current"] == pytest.approx(-0.1)


def test_a_series_that_only_rises_has_no_drawdowns():
    r = monthly([0.01] * 5)
    assert drawdowns(r).empty
    u = underwater_summary(r)
    assert u["time_underwater"] == 0.0 and u["longest_months"] == 0 and u["current"] == 0.0
