"""The splice used by extended/build.py must add no return of its own."""

import pandas as pd
import pytest

from build import splice, splice_frame


def daily(start, values):
    return pd.Series(values, index=pd.bdate_range(start, periods=len(values)), dtype=float)


def test_fund_returns_are_kept_before_the_join_and_etf_returns_after():
    fund = daily("2020-01-01", [10, 11, 12, 13, 14, 15])   # runs past the ETF's first day
    etf = daily("2020-01-06", [50, 55, 44])                  # starts on the fund's 4th day
    out, first = splice(etf, fund)
    assert first == pd.Timestamp("2020-01-06")
    assert list(out.index) == list(fund.index[:3]) + list(etf.index)
    # The fund's returns survive, rescaled to meet the ETF at 50 on the join day.
    assert out.iloc[:3].tolist() == pytest.approx([50 * 10 / 13, 50 * 11 / 13, 50 * 12 / 13])
    assert out.iloc[3:].tolist() == [50, 55, 44]
    # The return across the join is the fund's own return that day (12 -> 13).
    assert out.iloc[3] / out.iloc[2] == pytest.approx(13 / 12)


def test_fund_without_a_price_on_the_join_day_is_anchored_to_its_last_price():
    fund = daily("2020-01-01", [10, 20])                     # ends before the ETF starts
    etf = daily("2020-01-06", [100, 110])
    out, _ = splice(etf, fund)
    assert out.iloc[:2].tolist() == pytest.approx([50, 100])
    assert out.iloc[2:].tolist() == [100, 110]


def test_fund_that_starts_after_the_etf_is_rejected():
    fund = daily("2020-02-03", [10, 11])
    etf = daily("2020-01-06", [100, 110])
    with pytest.raises(ValueError):
        splice(etf, fund)


def test_splice_frame_keeps_the_funds_dividend_yield():
    fund = pd.DataFrame({"close": [20.0, 21.0, 22.0], "adj_close": [10.0, 10.5, 11.0], "dividend": [0.0, 0.42, 0.0]},
                        index=pd.bdate_range("2020-01-01", periods=3))
    etf = pd.DataFrame({"close": [110.0, 121.0], "adj_close": [50.0, 55.0], "dividend": [0.0, 1.1]},
                       index=pd.bdate_range("2020-01-03", periods=2))
    out, first = splice_frame(etf, fund)
    assert first == pd.Timestamp("2020-01-03")
    assert out["adj_close"].tolist() == pytest.approx([50 * 10 / 11, 50 * 10.5 / 11, 50, 55])
    # close and dividend are scaled by the same factor (110 / 22 = 5), so the
    # yield on the fund's ex-date is unchanged: 0.42 / 20 == 2.1 / 100.
    assert out["close"].tolist() == pytest.approx([100.0, 105.0, 110.0, 121.0])
    assert out["dividend"].tolist() == pytest.approx([0.0, 2.1, 0.0, 1.1])
