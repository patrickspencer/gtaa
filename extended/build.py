"""Build a price database that reaches back to 1999 by splicing a mutual fund
in front of each ETF.

    python extended/build.py                # writes extended.duckdb
    gtaa --db extended.duckdb backtest --top 6 --years

For every ETF in the universe, the proxy fund's daily total-return series is
used for the dates before the ETF's first trading day, scaled so that the two
series agree on that day. Each side's returns are therefore exactly the
fund's own; only the level is rescaled. The unadjusted close and the cash
dividends are scaled the same way, so the dividend yield the after-tax
analysis uses is also the fund's own. The spliced series is stored under
the ETF's symbol, so the ordinary signal query and backtest run on it without
knowing anything happened. A `sources` table records which fund supplied
which dates.

See README.md in this directory for why each proxy was chosen and what the
splice does to the results.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gtaa import data                    # noqa: E402
from gtaa.universe import ALL_SYMBOLS    # noqa: E402


@dataclass(frozen=True)
class Proxy:
    symbol: str      # the ETF in gtaa/universe.py
    fund: str        # the mutual fund used before the ETF exists
    note: str


PROXIES = (
    Proxy("VTV",  "VIVAX", "Vanguard Value Index Investor; VTV is a share class of the same fund"),
    Proxy("MTUM", "VFINX", "Vanguard 500 Index; no momentum fund existed, so plain large caps"),
    Proxy("VBR",  "VISVX", "Vanguard Small-Cap Value Index Investor; same fund as VBR"),
    Proxy("VB",   "NAESX", "Vanguard Small-Cap Index Investor; same fund as VB"),
    Proxy("VEA",  "VTMGX", "Vanguard Developed Markets Index; same fund as VEA"),
    Proxy("VWO",  "VEIEX", "Vanguard Emerging Markets Stock Index Investor; same fund as VWO"),
    Proxy("IEF",  "VFITX", "Vanguard Intermediate-Term Treasury Investor"),
    Proxy("TLT",  "VUSTX", "Vanguard Long-Term Treasury Investor"),
    Proxy("BWX",  "RPIBX", "T. Rowe Price International Bond, unhedged"),
    Proxy("LQD",  "VFICX", "Vanguard Intermediate-Term Investment-Grade Investor"),
    Proxy("DBC",  "QRAAX", "Oppenheimer Real Asset A, a GSCI-linked commodity fund (liquidated 2016)"),
    Proxy("GLD",  "FSAGX", "Fidelity Select Gold, a gold-mining equity fund; not bullion"),
    Proxy("VNQ",  "VGSIX", "Vanguard REIT Index Investor; same fund as VNQ"),
    Proxy("BIL",  "VFISX", "Vanguard Short-Term Treasury Investor; ~2-year duration, not T-bills"),
)

FETCH_FROM = "1998-01-01"

assert {p.symbol for p in PROXIES} == set(ALL_SYMBOLS), "every ETF needs a proxy"


def splice(etf: pd.Series, fund: pd.Series) -> tuple[pd.Series, pd.Timestamp]:
    """Prefix `etf` with `fund`, both daily adjusted closes indexed by date.

    The fund's values before the ETF's first day are multiplied by the ratio
    of the two on that day (or on the fund's last day at or before it), so
    the join introduces no return of its own. Returns the combined series
    and the first date that comes from the ETF.
    """
    etf, fund = etf.sort_index(), fund.sort_index()
    first = etf.index[0]
    anchor = fund[fund.index <= first]
    if anchor.empty:
        raise ValueError("the fund has no price on or before the ETF's first day")
    factor = etf.iloc[0] / anchor.iloc[-1]
    prefix = fund[fund.index < first] * factor
    return pd.concat([prefix, etf]), first


def frame(rows: list[dict]) -> pd.DataFrame:
    """Daily close, adjusted close and cash dividend per share, indexed by date."""
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"].str[:10])
    df["dividend"] = df["divCash"].fillna(0.0)
    return (df.set_index("date")[["close", "adjClose", "dividend"]]
              .rename(columns={"adjClose": "adj_close"}).astype(float).sort_index())


def splice_frame(etf: pd.DataFrame, fund: pd.DataFrame) -> tuple[pd.DataFrame, pd.Timestamp]:
    """Splice all three columns. The adjusted close is joined by `splice`;
    the unadjusted close and the dividend are scaled by one shared factor
    so that dividend / close (the yield the tax analysis needs) is the
    fund's own on every day."""
    adj, first = splice(etf["adj_close"], fund["adj_close"])
    anchor = fund["close"][fund.index <= first].iloc[-1]
    factor = etf["close"].iloc[0] / anchor
    prefix = fund[fund.index < first]
    close = pd.concat([prefix["close"] * factor, etf["close"]])
    dividend = pd.concat([prefix["dividend"] * factor, etf["dividend"]])
    return pd.DataFrame({"close": close, "adj_close": adj, "dividend": dividend}), first


def build(db: Path, client: data.TiingoClient | None = None) -> pd.DataFrame:
    client = client or data.TiingoClient()
    con = data.connect(db)
    con.execute("""
        CREATE TABLE IF NOT EXISTS sources (
            symbol VARCHAR, source VARCHAR, from_date DATE, to_date DATE,
            PRIMARY KEY (symbol, source)
        )
    """)
    report = []
    for p in PROXIES:
        etf = frame(client.daily_prices(p.symbol, FETCH_FROM))
        fund = frame(client.daily_prices(p.fund, FETCH_FROM))
        combined, first = splice_frame(etf, fund)
        con.execute("DELETE FROM prices WHERE symbol = ?", [p.symbol])
        con.execute("DELETE FROM sources WHERE symbol = ?", [p.symbol])
        con.executemany(
            "INSERT INTO prices VALUES (?, ?, ?, ?, ?)",
            [(p.symbol, d.date(), float(r.close), float(r.adj_close), float(r.dividend))
             for d, r in combined.iterrows()],
        )
        before = combined.index[combined.index < first]
        sources = [(p.symbol, p.symbol, first.date(), combined.index[-1].date())]
        if len(before):   # the fund contributed nothing if the ETF predates the fetch window
            sources.append((p.symbol, p.fund, before[0].date(), before[-1].date()))
        con.executemany("INSERT INTO sources VALUES (?, ?, ?, ?)", sources)
        report.append((p.symbol, p.fund, combined.index[0].date(), first.date()))
    con.close()
    return pd.DataFrame(report, columns=["symbol", "fund", "fund_from", "etf_from"])


def main(argv=None):
    ap = argparse.ArgumentParser(description="build the spliced 1999+ price database")
    ap.add_argument("--db", default="extended.duckdb")
    args = ap.parse_args(argv)
    report = build(Path(args.db))
    print(f"{'symbol':7s}{'fund':7s}{'fund from':12s}{'etf from':12s}")
    for r in report.itertuples(index=False):
        print(f"{r.symbol:7s}{r.fund:7s}{str(r.fund_from):12s}{str(r.etf_from):12s}")
    print(f"\nwritten to {args.db}")


if __name__ == "__main__":
    main()
