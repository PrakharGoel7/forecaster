"""Storage for completed forecasts and basket builds.
Supports PostgreSQL (DATABASE_URL env var) with SQLite fallback for local dev.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

DATABASE_URL = os.environ.get("DATABASE_URL", "") or os.environ.get("DATABASE_PUBLIC_URL", "")


def _use_pg() -> bool:
    return bool(DATABASE_URL)


def _pg_conn():
    import psycopg2
    import psycopg2.extras
    conn = psycopg2.connect(DATABASE_URL)
    return conn


def _sqlite_conn():
    import sqlite3
    path = Path(__file__).resolve().parent.parent / "forecasts.db"
    c = sqlite3.connect(str(path))
    c.row_factory = sqlite3.Row
    return c


def _conn():
    return _pg_conn() if _use_pg() else _sqlite_conn()


def _ph() -> str:
    """Placeholder character for parameterized queries."""
    return "%s" if _use_pg() else "?"


def _rows_to_dicts(rows, cursor=None) -> list[dict]:
    if _use_pg():
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row)) for row in rows]
    return [dict(r) for r in rows]


def _init():
    conn = _conn()
    try:
        cur = conn.cursor()
        p = _ph()
        if _use_pg():
            cur.execute("""
                CREATE TABLE IF NOT EXISTS forecasts (
                    id              SERIAL PRIMARY KEY,
                    created_at      TEXT    NOT NULL,
                    ticker          TEXT    NOT NULL,
                    event_title     TEXT,
                    question        TEXT    NOT NULL,
                    close_date      TEXT,
                    category        TEXT,
                    kalshi_price    REAL,
                    forecaster_prob REAL,
                    edge            REAL,
                    context_json    TEXT,
                    memo_json       TEXT    NOT NULL,
                    user_id         TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS baskets (
                    id                   SERIAL PRIMARY KEY,
                    created_at           TEXT    NOT NULL,
                    title                TEXT    NOT NULL,
                    summary              TEXT    NOT NULL,
                    core_belief          TEXT    NOT NULL,
                    mode                 TEXT    NOT NULL,
                    time_horizon         TEXT,
                    timeframe_start      TEXT,
                    timeframe_end        TEXT,
                    resolution_target    TEXT,
                    mechanism            TEXT,
                    scope                TEXT,
                    key_drivers_json     TEXT,
                    belief_summary_json  TEXT    NOT NULL,
                    analysis_json        TEXT    NOT NULL,
                    basket_json          TEXT    NOT NULL,
                    total_notional       REAL    NOT NULL,
                    screened_count       INTEGER,
                    is_public            BOOLEAN NOT NULL DEFAULT TRUE,
                    user_id              TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS basket_holdings (
                    id                     SERIAL PRIMARY KEY,
                    basket_id              INTEGER NOT NULL REFERENCES baskets(id) ON DELETE CASCADE,
                    ticker                 TEXT    NOT NULL,
                    event_ticker           TEXT,
                    question               TEXT    NOT NULL,
                    side                   TEXT    NOT NULL,
                    role                   TEXT    NOT NULL,
                    weight_dollars         REAL    NOT NULL,
                    rationale              TEXT,
                    main_risk              TEXT,
                    market_price_at_create REAL,
                    close_date             TEXT
                )
            """)
            # Safe migrations for existing tables
            for stmt in [
                "ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS user_id TEXT",
                "ALTER TABLE baskets ADD COLUMN IF NOT EXISTS user_id TEXT",
                "ALTER TABLE baskets ADD COLUMN IF NOT EXISTS is_public BOOLEAN NOT NULL DEFAULT TRUE",
            ]:
                try:
                    cur.execute(stmt)
                except Exception:
                    pass
        else:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS forecasts (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at      TEXT    NOT NULL,
                    ticker          TEXT    NOT NULL,
                    event_title     TEXT,
                    question        TEXT    NOT NULL,
                    close_date      TEXT,
                    category        TEXT,
                    kalshi_price    REAL,
                    forecaster_prob REAL,
                    edge            REAL,
                    context_json    TEXT,
                    memo_json       TEXT    NOT NULL,
                    user_id         TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS baskets (
                    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at           TEXT    NOT NULL,
                    title                TEXT    NOT NULL,
                    summary              TEXT    NOT NULL,
                    core_belief          TEXT    NOT NULL,
                    mode                 TEXT    NOT NULL,
                    time_horizon         TEXT,
                    timeframe_start      TEXT,
                    timeframe_end        TEXT,
                    resolution_target    TEXT,
                    mechanism            TEXT,
                    scope                TEXT,
                    key_drivers_json     TEXT,
                    belief_summary_json  TEXT    NOT NULL,
                    analysis_json        TEXT    NOT NULL,
                    basket_json          TEXT    NOT NULL,
                    total_notional       REAL    NOT NULL,
                    screened_count       INTEGER,
                    is_public            INTEGER NOT NULL DEFAULT 1,
                    user_id              TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS basket_holdings (
                    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
                    basket_id              INTEGER NOT NULL,
                    ticker                 TEXT    NOT NULL,
                    event_ticker           TEXT,
                    question               TEXT    NOT NULL,
                    side                   TEXT    NOT NULL,
                    role                   TEXT    NOT NULL,
                    weight_dollars         REAL    NOT NULL,
                    rationale              TEXT,
                    main_risk              TEXT,
                    market_price_at_create REAL,
                    close_date             TEXT,
                    FOREIGN KEY(basket_id) REFERENCES baskets(id) ON DELETE CASCADE
                )
            """)
            for col in ["user_id"]:
                try:
                    cur.execute(f"ALTER TABLE forecasts ADD COLUMN {col} TEXT")
                except Exception:
                    pass
            for col_def in [
                "user_id TEXT",
                "is_public INTEGER NOT NULL DEFAULT 1",
                "screened_count INTEGER",
            ]:
                try:
                    cur.execute(f"ALTER TABLE baskets ADD COLUMN {col_def}")
                except Exception:
                    pass
        conn.commit()
    finally:
        conn.close()


def save_forecast(*, ticker, event_title, question, close_date, category,
                  kalshi_price, memo, context_dict, user_id: str | None = None):
    _init()
    fp = memo.final_probability
    edge = fp - kalshi_price
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    p = _ph()
    conn = _conn()
    try:
        cur = conn.cursor()
        if _use_pg():
            cur.execute(f"""
                INSERT INTO forecasts
                    (created_at, ticker, event_title, question, close_date, category,
                     kalshi_price, forecaster_prob, edge, context_json, memo_json, user_id)
                VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p})
            """, (ts, ticker, event_title, question, close_date, category,
                  kalshi_price, fp, edge,
                  json.dumps(context_dict), memo.model_dump_json(), user_id))
        else:
            cur.execute(f"""
                INSERT INTO forecasts
                    (created_at, ticker, event_title, question, close_date, category,
                     kalshi_price, forecaster_prob, edge, context_json, memo_json, user_id)
                VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p})
            """, (ts, ticker, event_title, question, close_date, category,
                  kalshi_price, fp, edge,
                  json.dumps(context_dict), memo.model_dump_json(), user_id))
        conn.commit()
    finally:
        conn.close()


def get_forecasts(limit: int = 48, user_id: str | None = None):
    if not user_id:
        return []
    _init()
    p = _ph()
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT * FROM forecasts WHERE user_id = {p} ORDER BY created_at DESC LIMIT {p}",
            (user_id, limit)
        )
        rows = cur.fetchall()
        return _rows_to_dicts(rows, cur)
    finally:
        conn.close()


def save_basket(*, title, summary, core_belief, mode, time_horizon, timeframe_start,
                timeframe_end, resolution_target, mechanism, scope, key_drivers,
                belief_summary, analysis, basket, total_notional, screened_count,
                holdings, is_public: bool = True, user_id: str | None = None) -> int:
    _init()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    p = _ph()
    conn = _conn()
    try:
        cur = conn.cursor()
        basket_values = (
            ts, title, summary, core_belief, mode, time_horizon, timeframe_start,
            timeframe_end, resolution_target, mechanism, scope, json.dumps(key_drivers),
            json.dumps(belief_summary), json.dumps(analysis), json.dumps(basket),
            total_notional, screened_count, is_public, user_id,
        )
        if _use_pg():
            cur.execute(f"""
                INSERT INTO baskets
                    (created_at, title, summary, core_belief, mode, time_horizon,
                     timeframe_start, timeframe_end, resolution_target, mechanism, scope,
                     key_drivers_json, belief_summary_json, analysis_json, basket_json,
                     total_notional, screened_count, is_public, user_id)
                VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p})
                RETURNING id
            """, basket_values)
            basket_id = cur.fetchone()[0]
        else:
            cur.execute(f"""
                INSERT INTO baskets
                    (created_at, title, summary, core_belief, mode, time_horizon,
                     timeframe_start, timeframe_end, resolution_target, mechanism, scope,
                     key_drivers_json, belief_summary_json, analysis_json, basket_json,
                     total_notional, screened_count, is_public, user_id)
                VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p})
            """, basket_values)
            basket_id = cur.lastrowid

        for holding in holdings:
            cur.execute(f"""
                INSERT INTO basket_holdings
                    (basket_id, ticker, event_ticker, question, side, role, weight_dollars,
                     rationale, main_risk, market_price_at_create, close_date)
                VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p})
            """, (
                basket_id,
                holding.get("ticker"),
                holding.get("event_ticker"),
                holding.get("question"),
                holding.get("side"),
                holding.get("role"),
                holding.get("weight_dollars"),
                holding.get("rationale"),
                holding.get("main_risk"),
                holding.get("market_price"),
                holding.get("close_date"),
            ))
        conn.commit()
        return basket_id
    finally:
        conn.close()


def get_baskets(limit: int = 20, user_id: str | None = None, public_only: bool = False):
    _init()
    p = _ph()
    conn = _conn()
    try:
        cur = conn.cursor()
        clauses: list[str] = []
        params: list = []
        if user_id:
            clauses.append(f"user_id = {p}")
            params.append(user_id)
        elif public_only:
            clauses.append("is_public = 1" if not _use_pg() else "is_public = TRUE")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        cur.execute(
            f"SELECT * FROM baskets {where} ORDER BY created_at DESC LIMIT {p}",
            (*params, limit),
        )
        rows = _rows_to_dicts(cur.fetchall(), cur)
        return rows
    finally:
        conn.close()


def get_basket(basket_id: int, user_id: str | None = None):
    _init()
    p = _ph()
    conn = _conn()
    try:
        cur = conn.cursor()
        if user_id:
            cur.execute(f"SELECT * FROM baskets WHERE id = {p} AND (user_id = {p} OR is_public = {'TRUE' if _use_pg() else '1'})", (basket_id, user_id))
        else:
            cur.execute(f"SELECT * FROM baskets WHERE id = {p} AND is_public = {'TRUE' if _use_pg() else '1'}", (basket_id,))
        row = cur.fetchone()
        if not row:
            return None
        basket = _rows_to_dicts([row], cur)[0]
        cur.execute(f"SELECT * FROM basket_holdings WHERE basket_id = {p} ORDER BY weight_dollars DESC, id ASC", (basket_id,))
        basket["holdings"] = _rows_to_dicts(cur.fetchall(), cur)
        return basket
    finally:
        conn.close()
