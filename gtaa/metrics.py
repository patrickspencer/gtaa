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
    equity = (1.0 + monthly).cumprod()
    return float((equity / equity.cummax() - 1.0).min())


def calendar_year_returns(monthly: pd.Series) -> pd.Series:
    return (1.0 + monthly).groupby(monthly.index.year).prod() - 1.0


def summarise(monthly: pd.Series, cash: pd.Series) -> dict:
    return {
        "cagr": cagr(monthly),
        "volatility": annual_volatility(monthly),
        "sharpe": sharpe(monthly, cash),
        "max_drawdown": max_drawdown(monthly),
        "best_month": float(monthly.max()),
        "worst_month": float(monthly.min()),
    }
