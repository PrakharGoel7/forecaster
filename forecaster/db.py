"""SQLite storage for completed forecasts."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "forecasts.db"


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def _init():
    with _conn() as c:
        c.execute("""
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
                memo_json       TEXT    NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS trading_sessions (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at           TEXT    NOT NULL,
                core_belief          TEXT    NOT NULL,
                time_horizon         TEXT,
                scope                TEXT,
                key_drivers_json     TEXT,
                belief_summary_json  TEXT    NOT NULL,
                analysis_json        TEXT    NOT NULL,
                recommendations_json TEXT    NOT NULL
            )
        """)
        c.commit()


def save_forecast(*, ticker, event_title, question, close_date, category,
                  kalshi_price, memo, context_dict):
    _init()
    fp   = memo.final_probability
    edge = fp - kalshi_price
    ts   = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _conn() as c:
        c.execute("""
            INSERT INTO forecasts
                (created_at, ticker, event_title, question, close_date, category,
                 kalshi_price, forecaster_prob, edge, context_json, memo_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (ts, ticker, event_title, question, close_date, category,
              kalshi_price, fp, edge,
              json.dumps(context_dict), memo.model_dump_json()))
        c.commit()


def get_forecasts(limit: int = 48):
    _init()
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM forecasts ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def save_trading_session(*, core_belief, time_horizon, scope, key_drivers,
                         belief_summary, analysis, recommendations) -> int:
    _init()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _conn() as c:
        cur = c.execute("""
            INSERT INTO trading_sessions
                (created_at, core_belief, time_horizon, scope, key_drivers_json,
                 belief_summary_json, analysis_json, recommendations_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (ts, core_belief, time_horizon, scope,
              json.dumps(key_drivers),
              json.dumps(belief_summary),
              json.dumps(analysis),
              json.dumps(recommendations)))
        c.commit()
        return cur.lastrowid


def get_trading_sessions(limit: int = 20):
    _init()
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM trading_sessions ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]
