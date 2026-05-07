from __future__ import annotations

import re
import sqlite3

try:
    from .cache_paths import EVENTS_CACHE_DB_FILE
except ImportError:
    from cache_paths import EVENTS_CACHE_DB_FILE

_TOKEN_RE = re.compile(r"[A-Za-z0-9]{3,}")


def _conn() -> sqlite3.Connection:
    EVENTS_CACHE_DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(EVENTS_CACHE_DB_FILE))
    conn.row_factory = sqlite3.Row
    return conn


def rebuild_event_cache_db(events: list[dict]) -> None:
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("DROP TABLE IF EXISTS events")
        cur.execute("DROP TABLE IF EXISTS events_fts")
        cur.execute("""
            CREATE TABLE events (
                event_ticker  TEXT PRIMARY KEY,
                series_ticker TEXT NOT NULL,
                title         TEXT NOT NULL,
                sub_title     TEXT NOT NULL,
                category      TEXT NOT NULL
            )
        """)
        cur.execute("""
            CREATE VIRTUAL TABLE events_fts USING fts5(
                event_ticker UNINDEXED,
                series_ticker,
                title,
                sub_title,
                category,
                tokenize = 'porter unicode61'
            )
        """)
        rows = [
            (
                e.get("event_ticker", ""),
                e.get("series_ticker", ""),
                e.get("title", ""),
                e.get("sub_title", ""),
                e.get("category", ""),
            )
            for e in events
        ]
        cur.executemany(
            "INSERT INTO events (event_ticker, series_ticker, title, sub_title, category) VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        cur.executemany(
            "INSERT INTO events_fts (event_ticker, series_ticker, title, sub_title, category) VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def init_event_cache_db() -> None:
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("DROP TABLE IF EXISTS events")
        cur.execute("DROP TABLE IF EXISTS events_fts")
        cur.execute("""
            CREATE TABLE events (
                event_ticker  TEXT PRIMARY KEY,
                series_ticker TEXT NOT NULL,
                title         TEXT NOT NULL,
                sub_title     TEXT NOT NULL,
                category      TEXT NOT NULL
            )
        """)
        cur.execute("""
            CREATE VIRTUAL TABLE events_fts USING fts5(
                event_ticker UNINDEXED,
                series_ticker,
                title,
                sub_title,
                category,
                tokenize = 'porter unicode61'
            )
        """)
        conn.commit()
    finally:
        conn.close()


def append_events_to_cache_db(events: list[dict]) -> None:
    if not events:
        return
    rows = [
        (
            e.get("event_ticker", ""),
            e.get("series_ticker", ""),
            e.get("title", ""),
            e.get("sub_title", ""),
            e.get("category", ""),
        )
        for e in events
    ]
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.executemany(
            """
            INSERT OR REPLACE INTO events
            (event_ticker, series_ticker, title, sub_title, category)
            VALUES (?, ?, ?, ?, ?)
            """,
            rows,
        )
        cur.executemany(
            """
            INSERT INTO events_fts
            (event_ticker, series_ticker, title, sub_title, category)
            VALUES (?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def _require_db() -> None:
    if not EVENTS_CACHE_DB_FILE.exists():
        raise FileNotFoundError(
            f"Event cache DB not found at {EVENTS_CACHE_DB_FILE}. "
            "Run `python sync_events.py` first."
        )


def load_all_events(limit: int | None = None, category: str | None = None) -> list[dict]:
    _require_db()
    conn = _conn()
    try:
        cur = conn.cursor()
        query = """
            SELECT event_ticker, series_ticker, title, sub_title, category
            FROM events
        """
        params: list[str | int] = []
        if category:
            query += " WHERE category = ?"
            params.append(category)
        query += " ORDER BY category, event_ticker"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        cur.execute(query, tuple(params))
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def search_events_fts(query_text: str, limit: int = 1200) -> list[dict]:
    _require_db()
    terms = []
    seen: set[str] = set()
    for token in _TOKEN_RE.findall(query_text.lower()):
        if token not in seen:
            seen.add(token)
            terms.append(token)
    if not terms:
        return []
    fts_query = " OR ".join(f'"{t}"' for t in terms[:24])
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT e.event_ticker, e.series_ticker, e.title, e.sub_title, e.category
            FROM events_fts f
            JOIN events e ON e.event_ticker = f.event_ticker
            WHERE events_fts MATCH ?
            ORDER BY bm25(events_fts), e.event_ticker
            LIMIT ?
            """,
            (fts_query, limit),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def list_event_categories() -> list[str]:
    _require_db()
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT DISTINCT category
            FROM events
            WHERE trim(category) <> ''
            ORDER BY category
            """
        )
        return [row["category"] for row in cur.fetchall()]
    finally:
        conn.close()


def search_events(query_text: str, limit: int = 48, category: str | None = None) -> list[dict]:
    _require_db()
    q = query_text.strip().lower()
    if not q:
        return load_all_events(limit=limit, category=category)

    conn = _conn()
    try:
        cur = conn.cursor()
        like = f"%{q}%"
        category_clause = "AND category = ?" if category else ""
        params: list[str | int] = [like, like, like, like, like]
        if category:
            params.append(category)
        params.append(limit)
        cur.execute(
            f"""
            SELECT event_ticker, series_ticker, title, sub_title, category
            FROM events
            WHERE (
                   lower(title) LIKE ?
                OR lower(sub_title) LIKE ?
                OR lower(event_ticker) LIKE ?
                OR lower(series_ticker) LIKE ?
                OR lower(category) LIKE ?
            )
               {category_clause}
            ORDER BY category, event_ticker
            LIMIT ?
            """,
            tuple(params),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_event_lookup(event_tickers: list[str] | None = None) -> dict[str, dict]:
    _require_db()
    conn = _conn()
    try:
        cur = conn.cursor()
        if event_tickers:
            placeholders = ",".join("?" for _ in event_tickers)
            cur.execute(
                f"""
                SELECT event_ticker, series_ticker, title, sub_title, category
                FROM events
                WHERE event_ticker IN ({placeholders})
                """,
                event_tickers,
            )
        else:
            cur.execute("""
                SELECT event_ticker, series_ticker, title, sub_title, category
                FROM events
            """)
        return {row["event_ticker"]: dict(row) for row in cur.fetchall()}
    finally:
        conn.close()
