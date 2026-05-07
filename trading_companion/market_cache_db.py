from __future__ import annotations

import sqlite3

try:
    from .cache_paths import MARKETS_CACHE_DB_FILE
except ImportError:
    from cache_paths import MARKETS_CACHE_DB_FILE


def _conn() -> sqlite3.Connection:
    MARKETS_CACHE_DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(MARKETS_CACHE_DB_FILE))
    conn.row_factory = sqlite3.Row
    return conn


def init_market_cache_db() -> None:
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("DROP TABLE IF EXISTS markets")
        cur.execute("""
            CREATE TABLE markets (
                ticker         TEXT PRIMARY KEY,
                event_ticker   TEXT NOT NULL,
                question       TEXT NOT NULL,
                yes_sub_title  TEXT NOT NULL,
                no_sub_title   TEXT NOT NULL,
                yes_bid        REAL NOT NULL,
                yes_ask        REAL NOT NULL,
                last_price     REAL NOT NULL,
                mid_price      REAL NOT NULL,
                volume         REAL NOT NULL,
                status         TEXT NOT NULL,
                close_time     TEXT NOT NULL,
                close_date     TEXT NOT NULL,
                rules_primary  TEXT NOT NULL,
                rules_secondary TEXT NOT NULL
            )
        """)
        cur.execute("CREATE INDEX idx_markets_event_ticker ON markets(event_ticker)")
        conn.commit()
    finally:
        conn.close()


def append_markets_to_cache_db(markets: list[dict]) -> None:
    if not markets:
        return
    rows = [
        (
            m.get("ticker", ""),
            m.get("event_ticker", ""),
            m.get("question", ""),
            m.get("yes_sub_title", ""),
            m.get("no_sub_title", ""),
            m.get("yes_bid", 0.0),
            m.get("yes_ask", 0.0),
            m.get("last_price", 0.0),
            m.get("mid_price", 0.0),
            m.get("volume", 0.0),
            m.get("status", ""),
            m.get("close_time", ""),
            m.get("close_date", ""),
            m.get("rules_primary", ""),
            m.get("rules_secondary", ""),
        )
        for m in markets
    ]
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.executemany(
            """
            INSERT OR REPLACE INTO markets
            (ticker, event_ticker, question, yes_sub_title, no_sub_title, yes_bid, yes_ask,
             last_price, mid_price, volume, status, close_time, close_date, rules_primary, rules_secondary)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def get_markets_for_events(event_tickers: list[str]) -> list[dict]:
    if not MARKETS_CACHE_DB_FILE.exists():
        raise FileNotFoundError(
            f"Market cache DB not found at {MARKETS_CACHE_DB_FILE}. "
            "Run `python sync_markets.py` first."
        )
    if not event_tickers:
        return []
    conn = _conn()
    try:
        cur = conn.cursor()
        placeholders = ",".join("?" for _ in event_tickers)
        cur.execute(
            f"""
            SELECT ticker, event_ticker, question, yes_sub_title, no_sub_title, yes_bid, yes_ask,
                   last_price, mid_price, volume, status, close_time, close_date, rules_primary, rules_secondary
            FROM markets
            WHERE event_ticker IN ({placeholders})
            ORDER BY event_ticker, volume DESC, ticker
            """,
            event_tickers,
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_all_markets(limit: int | None = None, status: str = "open") -> list[dict]:
    if not MARKETS_CACHE_DB_FILE.exists():
        raise FileNotFoundError(
            f"Market cache DB not found at {MARKETS_CACHE_DB_FILE}. "
            "Run `python sync_markets.py` first."
        )
    conn = _conn()
    try:
        cur = conn.cursor()
        query = """
            SELECT ticker, event_ticker, question, yes_sub_title, no_sub_title, yes_bid, yes_ask,
                   last_price, mid_price, volume, status, close_time, close_date, rules_primary, rules_secondary
            FROM markets
        """
        params: list[str | int] = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY volume DESC, close_date, ticker"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        cur.execute(query, tuple(params))
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
