from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from cache_paths import EVENTS_CACHE_DB_FILE, EVENTS_CACHE_FILE

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


def _load_events_from_json() -> list[dict]:
    if not EVENTS_CACHE_FILE.exists():
        return []
    data = json.loads(EVENTS_CACHE_FILE.read_text())
    return data.get("events", [])


def load_all_events() -> list[dict]:
    if EVENTS_CACHE_DB_FILE.exists():
        conn = _conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT event_ticker, series_ticker, title, sub_title, category
                FROM events
                ORDER BY category, event_ticker
            """)
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()
    return _load_events_from_json()


def search_events_fts(query_text: str, limit: int = 1200) -> list[dict]:
    if not EVENTS_CACHE_DB_FILE.exists():
        return []
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


def get_event_lookup(event_tickers: list[str] | None = None) -> dict[str, dict]:
    if EVENTS_CACHE_DB_FILE.exists():
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

    events = _load_events_from_json()
    if event_tickers:
        wanted = set(event_tickers)
        events = [e for e in events if e.get("event_ticker", "") in wanted]
    return {e["event_ticker"]: e for e in events}
