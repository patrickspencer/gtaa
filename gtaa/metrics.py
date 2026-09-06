"""Performance statistics on a series of monthly returns."""

from __future__ import annotations

import math

import pandas as pd

MONTHS = 12


def cagr(monthly: pd.Series) -> float:
    growth = float((1.0 + monthly).prod())
    years = len(monthly) / MONTHS
    return growth ** (1.0 / years) - 1.0 if years > 0 and growth > 0 else float("nan")


def annual_volatility(monthly: pd.Series) -> float:
    return float(monthly.std(ddof=1)) * math.sqrt(MONTHS)


def sharpe(monthly: pd.Series, cash: pd.Series) -> float:
    """Annualised Sharpe ratio using the cash proxy as the risk-free rate."""
    excess = monthly - cash.reindex(monthly.index).fillna(0.0)
    vol = excess.std(ddof=1)
    return float(excess.mean() / vol * math.sqrt(MONTHS)) if vol > 0 else float("nan")


def max_drawdown(monthly: pd.Series) -> float:
    """The deepest fall from a previous high, counting the starting value as
    a high (so a decline that begins in the first month is measured)."""
    equity = (1.0 + monthly).cumprod()
    peak = equity.cummax().clip(lower=1.0)
    return float((equity / peak - 1.0).min())


def calendar_year_returns(monthly: pd.Series) -> pd.Series:
    return (1.0 + monthly).groupby(monthly.index.year).prod() - 1.0


def rolling_returns(monthly: pd.Series, months: int) -> pd.Series:
    """Annualised return of every window of `months` consecutive months,
    indexed by the month the window ends in."""
    growth = (1.0 + monthly).rolling(months).apply(lambda w: w.prod(), raw=True).dropna()
    return growth ** (MONTHS / months) - 1.0


def rolling_summary(monthly: pd.Series, windows=(12, 36, 60)) -> list[dict]:
    """Best, worst and median annualised return over each window length,
    with the months each extreme window spans."""
    out = []
    for months in windows:
        r = rolling_returns(monthly, months)
        if r.empty:
            continue

        def span(end):
            start = end - pd.DateOffset(months=months - 1)
            return start.strftime("%Y-%m"), end.strftime("%Y-%m")

        out.append({
            "months": months,
            "windows": len(r),
            "best": float(r.max()), "best_span": span(r.idxmax()),
            "worst": float(r.min()), "worst_span": span(r.idxmin()),
            "median": float(r.median()),
            "positive": float((r > 0).mean()),
        })
    return out


def _underwater(monthly: pd.Series) -> pd.Series:
    """Equity relative to its running peak (0 at a high, negative below),
    with a starting point one month before the first return."""
    start = monthly.index[0] - pd.DateOffset(months=1)
    equity = pd.concat([pd.Series([1.0], index=[start]), (1.0 + monthly).cumprod()])
    return equity / equity.cummax() - 1.0


def drawdowns(monthly: pd.Series) -> pd.DataFrame:
    """Every stretch spent below a previous equity peak, deepest first.

    Columns: peak (last month at the high), trough, recovery (first month
    back at the high, or NaT if still underwater), depth, months from the
    peak to the trough, months from the trough to recovery (None if not
    recovered), and months from the peak to recovery (or to the last month).
    """
    under = _underwater(monthly)
    episodes, i, n = [], 0, len(under)
    while i < n:
        if under.iloc[i] >= 0:
            i += 1
            continue
        peak, j = i - 1, i
        while j < n and under.iloc[j] < 0:
            j += 1
        t = int(under.iloc[i:j].values.argmin()) + i
        recovered = j < n
        episodes.append({
            "peak": under.index[peak],
            "trough": under.index[t],
            "recovery": under.index[j] if recovered else pd.NaT,
            "depth": float(under.iloc[t]),
            "months_to_trough": t - peak,
            "months_to_recover": (j - t) if recovered else None,
            "months": (j if recovered else n - 1) - peak,
        })
        i = j
    cols = ["peak", "trough", "recovery", "depth", "months_to_trough", "months_to_recover", "months"]
    return pd.DataFrame(episodes, columns=cols).sort_values("depth").reset_index(drop=True)


def underwater_summary(monthly: pd.Series) -> dict:
    """The share of months spent below a previous peak, the longest such
    stretch, and where the portfolio stands now."""
    under = _underwater(monthly).iloc[1:]
    dd = drawdowns(monthly)
    longest = dd.loc[dd["months"].idxmax()] if not dd.empty else None
    return {
        "time_underwater": float((under < 0).mean()),
        "longest_months": int(longest["months"]) if longest is not None else 0,
        "longest_span": (longest["peak"], longest["recovery"]) if longest is not None else None,
        "current": float(under.iloc[-1]),
    }


def summarise(monthly: pd.Series, cash: pd.Series) -> dict:
    return {
        "cagr": cagr(monthly),
        "volatility": annual_volatility(monthly),
        "sharpe": sharpe(monthly, cash),
        "max_drawdown": max_drawdown(monthly),
        "best_month": float(monthly.max()),
        "worst_month": float(monthly.min()),
    }
