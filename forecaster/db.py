"""Storage for completed forecasts and trading sessions.
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
                CREATE TABLE IF NOT EXISTS trading_sessions (
                    id                   SERIAL PRIMARY KEY,
                    created_at           TEXT    NOT NULL,
                    core_belief          TEXT    NOT NULL,
                    time_horizon         TEXT,
                    scope                TEXT,
                    key_drivers_json     TEXT,
                    belief_summary_json  TEXT    NOT NULL,
                    analysis_json        TEXT    NOT NULL,
                    recommendations_json TEXT    NOT NULL,
                    user_id              TEXT
                )
            """)
            # Safe migrations for existing tables
            for stmt in [
                "ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS user_id TEXT",
                "ALTER TABLE trading_sessions ADD COLUMN IF NOT EXISTS user_id TEXT",
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
                CREATE TABLE IF NOT EXISTS trading_sessions (
                    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at           TEXT    NOT NULL,
                    core_belief          TEXT    NOT NULL,
                    time_horizon         TEXT,
                    scope                TEXT,
                    key_drivers_json     TEXT,
                    belief_summary_json  TEXT    NOT NULL,
                    analysis_json        TEXT    NOT NULL,
                    recommendations_json TEXT    NOT NULL,
                    user_id              TEXT
                )
            """)
            for col in ["user_id"]:
                try:
                    cur.execute(f"ALTER TABLE forecasts ADD COLUMN {col} TEXT")
                except Exception:
                    pass
                try:
                    cur.execute(f"ALTER TABLE trading_sessions ADD COLUMN {col} TEXT")
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
    _init()
    p = _ph()
    conn = _conn()
    try:
        cur = conn.cursor()
        if user_id:
            cur.execute(
                f"SELECT * FROM forecasts WHERE user_id = {p} ORDER BY created_at DESC LIMIT {p}",
                (user_id, limit)
            )
        else:
            cur.execute(
                f"SELECT * FROM forecasts ORDER BY created_at DESC LIMIT {p}",
                (limit,)
            )
        rows = cur.fetchall()
        return _rows_to_dicts(rows, cur)
    finally:
        conn.close()


def save_trading_session(*, core_belief, time_horizon, scope, key_drivers,
                         belief_summary, analysis, recommendations,
                         user_id: str | None = None) -> int:
    _init()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    p = _ph()
    conn = _conn()
    try:
        cur = conn.cursor()
        if _use_pg():
            cur.execute(f"""
                INSERT INTO trading_sessions
                    (created_at, core_belief, time_horizon, scope, key_drivers_json,
                     belief_summary_json, analysis_json, recommendations_json, user_id)
                VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p})
                RETURNING id
            """, (ts, core_belief, time_horizon, scope,
                  json.dumps(key_drivers),
                  json.dumps(belief_summary),
                  json.dumps(analysis),
                  json.dumps(recommendations),
                  user_id))
            row = cur.fetchone()
            conn.commit()
            return row[0]
        else:
            cur.execute(f"""
                INSERT INTO trading_sessions
                    (created_at, core_belief, time_horizon, scope, key_drivers_json,
                     belief_summary_json, analysis_json, recommendations_json, user_id)
                VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p})
            """, (ts, core_belief, time_horizon, scope,
                  json.dumps(key_drivers),
                  json.dumps(belief_summary),
                  json.dumps(analysis),
                  json.dumps(recommendations),
                  user_id))
            conn.commit()
            return cur.lastrowid
    finally:
        conn.close()


def get_trading_sessions(limit: int = 20, user_id: str | None = None):
    _init()
    p = _ph()
    conn = _conn()
    try:
        cur = conn.cursor()
        if user_id:
            cur.execute(
                f"SELECT * FROM trading_sessions WHERE user_id = {p} ORDER BY created_at DESC LIMIT {p}",
                (user_id, limit)
            )
        else:
            cur.execute(
                f"SELECT * FROM trading_sessions ORDER BY created_at DESC LIMIT {p}",
                (limit,)
            )
        rows = cur.fetchall()
        return _rows_to_dicts(rows, cur)
    finally:
        conn.close()
