"""Price storage and retrieval.

Daily prices live in a DuckDB file with one table:

    prices(symbol VARCHAR, date DATE, close DOUBLE, adj_close DOUBLE, dividend DOUBLE)

`adj_close` is the dividend- and split-adjusted close, which makes
consecutive values a total-return series, the quantity Faber's rules are
defined on. Everything downstream (month-end closes, momentum, moving
averages, the backtest) is computed from this table with SQL. `dividend`
is the cash distribution per share paid that day (zero on other days); it
is only used by the after-tax analysis, which needs to know how much of
each month's return arrived as a taxable distribution.

Prices come from Tiingo (https://www.tiingo.com), which needs a free API key
in the TIINGO_API_KEY environment variable. Nothing else in the project
touches the network.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Iterable

import duckdb
import requests

TIINGO_URL = "https://api.tiingo.com/tiingo/daily/{symbol}/prices"
DEFAULT_DB = Path(os.environ.get("GTAA_DB", "gtaa.duckdb"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS prices (
    symbol    VARCHAR NOT NULL,
    date      DATE    NOT NULL,
    close     DOUBLE  NOT NULL,
    adj_close DOUBLE  NOT NULL,
    dividend  DOUBLE  NOT NULL DEFAULT 0,
    PRIMARY KEY (symbol, date)
);
"""


def connect(path: Path | str = DEFAULT_DB) -> duckdb.DuckDBPyConnection:
    """Open (creating if needed) the price database."""
    con = duckdb.connect(str(path))
    con.execute(SCHEMA)
    # Databases built before the dividend column existed.
    con.execute("ALTER TABLE prices ADD COLUMN IF NOT EXISTS dividend DOUBLE DEFAULT 0")
    return con


class TiingoClient:
    def __init__(self, api_key: str | None = None, session: requests.Session | None = None):
        self.api_key = api_key or os.environ.get("TIINGO_API_KEY")
        if not self.api_key:
            raise RuntimeError("Set TIINGO_API_KEY (free key at https://www.tiingo.com)")
        self.session = session or requests.Session()

    def daily_prices(self, symbol: str, start: str = "1990-01-01") -> list[dict]:
        """Daily rows for a symbol from `start` to today: date, close, adjClose, divCash."""
        resp = self.session.get(
            TIINGO_URL.format(symbol=symbol),
            params={"startDate": start, "format": "json", "resampleFreq": "daily"},
            headers={"Authorization": f"Token {self.api_key}"},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()


def store_prices(con: duckdb.DuckDBPyConnection, symbol: str, rows: Iterable[dict]) -> int:
    """Upsert Tiingo rows for one symbol. Returns the number of rows written."""
    records = [
        (symbol, r["date"][:10], float(r["close"]), float(r["adjClose"]), float(r.get("divCash") or 0.0))
        for r in rows
        if r.get("close") is not None and r.get("adjClose") is not None
    ]
    if not records:
        return 0
    con.executemany(
        "INSERT OR REPLACE INTO prices (symbol, date, close, adj_close, dividend) VALUES (?, ?, ?, ?, ?)",
        records,
    )
    return len(records)


def update_prices(
    con: duckdb.DuckDBPyConnection,
    symbols: Iterable[str],
    client: TiingoClient | None = None,
    start: str = "1990-01-01",
) -> dict[str, int]:
    """Refresh every symbol's full history.

    The whole history is re-fetched each time on purpose: adjusted closes
    change retroactively whenever a dividend or split occurs, so only a full
    refresh keeps the total-return series consistent.
    """
    client = client or TiingoClient()
    written = {}
    for symbol in symbols:
        written[symbol] = store_prices(con, symbol, client.daily_prices(symbol, start))
    return written


def coverage(con: duckdb.DuckDBPyConnection) -> list[tuple[str, date, date, int]]:
    """(symbol, first date, last date, row count) for every stored symbol."""
    return con.execute(
        "SELECT symbol, MIN(date), MAX(date), COUNT(*) FROM prices GROUP BY symbol ORDER BY symbol"
    ).fetchall()
