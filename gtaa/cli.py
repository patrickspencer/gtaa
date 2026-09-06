"""Command-line interface.

    gtaa update                 fetch/refresh prices for the whole universe
    gtaa signal --top 6         the current allocation (also --top 3)
    gtaa backtest --top 6       run the backtest and print a summary
    gtaa coverage               what price history is stored
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

from . import data
from .backtest import run_backtest
from .signals import allocation, compute_signals
from .universe import ALL_SYMBOLS, CASH, asset


def cmd_update(args):
    con = data.connect(args.db)
    written = data.update_prices(con, ALL_SYMBOLS, start=args.start)
    for symbol, n in written.items():
        print(f"{symbol:6s} {n:6d} rows")


def cmd_coverage(args):
    con = data.connect(args.db)
    for symbol, first, last, n in data.coverage(con):
        print(f"{symbol:6s} {first} .. {last}  ({n} days)")


def cmd_signal(args):
    con = data.connect(args.db)
    signals = compute_signals(con)
    if signals.empty:
        sys.exit("No signals: run `gtaa update` first.")
    rows, cash, month = allocation(signals, args.top, args.month)
    latest = signals[signals["month"] == month].iloc[0]
    status = "complete" if latest["month_complete"] else "provisional (month not finished)"
    print(f"GTAA AGG {args.top}, decided at {latest['month_end'].date()} ({status})\n")
    print(f"{'rank':>4}  {'symbol':6s} {'asset class':28s} {'score':>8s}  {'vs 10mo SMA':12s} {'weight':>7s}")
    for _, r in rows.iterrows():
        trend = "above" if r["above_sma"] else "below -> cash"
        print(f"{int(r['rank']):>4}  {r['symbol']:6s} {asset(r['symbol']).asset_class:28s} "
              f"{r['score']:>8.2%}  {trend:12s} {r['weight']:>7.1%}")
    print(f"{'':>4}  {CASH.symbol:6s} {CASH.asset_class:28s} {'':>8s}  {'':12s} {cash:>7.1%}")
    if args.all:
        print("\nFull ranking:")
        month_rows = signals[signals["month"] == month]
        for _, r in month_rows.iterrows():
            print(f"{int(r['rank']):>4}  {r['symbol']:6s} {r['score']:>8.2%}  "
                  f"{'above' if r['above_sma'] else 'below'}")


def cmd_backtest(args):
    con = data.connect(args.db)
    result = run_backtest(con, args.top, start=args.start, end=args.end)
    s = result.summary
    n = len(result.weights.columns) - 1
    print(f"GTAA AGG {args.top}: {s['start']} to {s['end']} ({s['months']} months, month-end to month-end)\n")

    def block(title, m):
        print(title)
        print(f"  {'CAGR':22s}{m['cagr']:>9.2%}")
        print(f"  {'Max drawdown':22s}{m['max_drawdown']:>9.2%}")
        print(f"  {'Volatility (annual)':22s}{m['volatility']:>9.2%}")
        print(f"  {'Sharpe (vs T-bills)':22s}{m['sharpe']:>9.2f}")
        print(f"  {'Best month':22s}{m['best_month']:>9.2%}")
        print(f"  {'Worst month':22s}{m['worst_month']:>9.2%}")

    block(f"Strategy (top {args.top} by momentum, trend filter, rest in cash)", s)
    print(f"  {'Average cash weight':22s}{s['avg_cash_weight']:>9.1%}")
    print()
    block(f"Equal-weight (all {n} held at once, 1/{n} each, rebalanced monthly)", s["equal_weight"])
    if args.years:
        from .metrics import calendar_year_returns
        yrs = calendar_year_returns(result.returns)
        bench = (1.0 + result.benchmark.pct_change().dropna()).groupby(
            result.benchmark.index[1:].year).prod() - 1.0
        first_month, last_month = result.returns.index[0], result.returns.index[-1]
        print(f"\nCalendar years:\n  {'':6s}{'strategy':>9s}   {'equal-weight':>12s}")
        for year, r in yrs.items():
            partial = ""
            if year == last_month.year and last_month.month != 12:
                partial = "  (to %s)" % last_month.strftime("%b")
            elif year == first_month.year and first_month.month != 1:
                partial = "  (from %s)" % first_month.strftime("%b")
            print(f"  {year}  {r:>9.2%}   {bench.get(year, float('nan')):>12.2%}{partial}")
    if args.csv:
        out = pd.DataFrame({"equity": result.equity, "equal_weight": result.benchmark})
        out.to_csv(args.csv, index_label="month_end")
        print(f"\nEquity curves written to {args.csv}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="gtaa", description="GTAA AGG 3 / AGG 6 signals and backtest")
    p.add_argument("--db", default=str(data.DEFAULT_DB), help="DuckDB file (default: gtaa.duckdb or $GTAA_DB)")
    sub = p.add_subparsers(dest="cmd", required=True)

    u = sub.add_parser("update", help="fetch prices from Tiingo")
    u.add_argument("--start", default="1990-01-01")
    u.set_defaults(fn=cmd_update)

    c = sub.add_parser("coverage", help="show stored price history")
    c.set_defaults(fn=cmd_coverage)

    s = sub.add_parser("signal", help="current allocation")
    s.add_argument("--top", type=int, choices=(3, 6), default=6)
    s.add_argument("--month", default=None, help="YYYY-MM-01 to show a past month's decision")
    s.add_argument("--all", action="store_true", help="also print the full ranking")
    s.set_defaults(fn=cmd_signal)

    b = sub.add_parser("backtest", help="run the monthly backtest")
    b.add_argument("--top", type=int, choices=(3, 6), default=6)
    b.add_argument("--start", default=None, help="YYYY-MM-DD")
    b.add_argument("--end", default=None, help="YYYY-MM-DD")
    b.add_argument("--years", action="store_true", help="print calendar-year returns")
    b.add_argument("--csv", default=None, help="write equity curves to this file")
    b.set_defaults(fn=cmd_backtest)

    args = p.parse_args(argv)
    if getattr(args, "month", None):
        args.month = pd.Timestamp(args.month)
    args.fn(args)


if __name__ == "__main__":
    main()
