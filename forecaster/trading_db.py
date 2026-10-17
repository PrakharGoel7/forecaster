"""Persistence for user Kalshi connections and Prism-attributed basket trades.

Only confirmed Kalshi fills contribute to invested totals.  The application
never stores a private key outside its encrypted credential row.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from forecaster import db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _init() -> None:
    conn = db._conn()
    try:
        cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS kalshi_connections (
            user_id TEXT PRIMARY KEY, key_id_ciphertext TEXT NOT NULL,
            private_key_ciphertext TEXT NOT NULL, key_id_masked TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS trade_previews (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL, basket_id INTEGER NOT NULL,
            created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
            status TEXT NOT NULL, payload_json TEXT NOT NULL)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS basket_investments (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL, basket_id INTEGER NOT NULL,
            preview_id TEXT UNIQUE NOT NULL, created_at TEXT NOT NULL,
            status TEXT NOT NULL)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS basket_orders (
            id TEXT PRIMARY KEY, investment_id TEXT NOT NULL, user_id TEXT NOT NULL,
            basket_id INTEGER NOT NULL, ticker TEXT NOT NULL, side TEXT NOT NULL,
            client_order_id TEXT UNIQUE NOT NULL, order_id TEXT,
            count TEXT NOT NULL, limit_price_dollars TEXT NOT NULL,
            status TEXT NOT NULL, error TEXT, created_at TEXT NOT NULL)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS basket_fills (
            fill_id TEXT PRIMARY KEY, investment_id TEXT NOT NULL,
            user_id TEXT NOT NULL, basket_id INTEGER NOT NULL,
            order_id TEXT NOT NULL, ticker TEXT NOT NULL, side TEXT NOT NULL,
            count TEXT NOT NULL, price_dollars TEXT NOT NULL,
            fee_dollars TEXT NOT NULL, cost_dollars TEXT NOT NULL,
            created_at TEXT NOT NULL)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS portfolio_snapshots (
            user_id TEXT NOT NULL, snapshot_date TEXT NOT NULL,
            invested_dollars TEXT NOT NULL, current_value_dollars TEXT,
            PRIMARY KEY(user_id, snapshot_date))""")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_basket_fills_basket ON basket_fills(basket_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_basket_fills_user ON basket_fills(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_basket_orders_user ON basket_orders(user_id)")
        conn.commit()
    finally:
        conn.close()


def _one(sql: str, params=()) -> dict | None:
    _init()
    conn = db._conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        row = cur.fetchone()
        return db._rows_to_dicts([row], cur)[0] if row else None
    finally:
        conn.close()


def _many(sql: str, params=()) -> list[dict]:
    _init()
    conn = db._conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        return db._rows_to_dicts(cur.fetchall(), cur)
    finally:
        conn.close()


def put_connection(user_id: str, key_id_ciphertext: str, private_key_ciphertext: str, key_id_masked: str) -> None:
    _init()
    p = db._ph()
    conn = db._conn()
    try:
        cur = conn.cursor()
        cur.execute(f"DELETE FROM kalshi_connections WHERE user_id={p}", (user_id,))
        now = _now()
        cur.execute(f"INSERT INTO kalshi_connections VALUES ({','.join([p]*6)})",
                    (user_id, key_id_ciphertext, private_key_ciphertext, key_id_masked, now, now))
        conn.commit()
    finally:
        conn.close()


def get_connection(user_id: str) -> dict | None:
    return _one(f"SELECT * FROM kalshi_connections WHERE user_id={db._ph()}", (user_id,))


def delete_connection(user_id: str) -> None:
    _init()
    conn = db._conn()
    try:
        cur = conn.cursor()
        cur.execute(f"DELETE FROM kalshi_connections WHERE user_id={db._ph()}", (user_id,))
        conn.commit()
    finally:
        conn.close()


def create_preview(preview_id: str, user_id: str, basket_id: int, expires_at: str, payload: dict) -> None:
    _init()
    p = db._ph()
    conn = db._conn()
    try:
        cur = conn.cursor()
        cur.execute(f"INSERT INTO trade_previews VALUES ({','.join([p]*7)})",
                    (preview_id, user_id, basket_id, _now(), expires_at, "open", json.dumps(payload)))
        conn.commit()
    finally:
        conn.close()


def get_preview(preview_id: str, user_id: str, basket_id: int) -> dict | None:
    p = db._ph()
    return _one(f"SELECT * FROM trade_previews WHERE id={p} AND user_id={p} AND basket_id={p}",
                (preview_id, user_id, basket_id))


def claim_preview(preview_id: str, user_id: str, basket_id: int, investment_id: str) -> bool:
    """Atomically prevent retries from sending duplicate orders."""
    _init()
    p = db._ph()
    conn = db._conn()
    try:
        cur = conn.cursor()
        now = _now()
        cur.execute(f"UPDATE trade_previews SET status='claimed' WHERE id={p} AND user_id={p} "
                    f"AND basket_id={p} AND status='open' AND expires_at>{p}",
                    (preview_id, user_id, basket_id, now))
        if cur.rowcount != 1:
            conn.rollback()
            return False
        cur.execute(f"INSERT INTO basket_investments VALUES ({','.join([p]*6)})",
                    (investment_id, user_id, basket_id, preview_id, now, "pending_reconciliation"))
        conn.commit()
        return True
    finally:
        conn.close()


def insert_order(order: dict) -> None:
    _init()
    p = db._ph()
    conn = db._conn()
    try:
        cur = conn.cursor()
        cur.execute(f"INSERT INTO basket_orders VALUES ({','.join([p]*13)})",
                    (order["id"], order["investment_id"], order["user_id"], order["basket_id"],
                     order["ticker"], order["side"], order["client_order_id"], None,
                     str(order["count"]), str(order["limit_price_dollars"]), "submitting", None, _now()))
        conn.commit()
    finally:
        conn.close()


def update_order(client_order_id: str, *, order_id: str | None, status: str, error: str | None = None) -> None:
    _init()
    p = db._ph()
    conn = db._conn()
    try:
        cur = conn.cursor()
        cur.execute(f"UPDATE basket_orders SET order_id={p}, status={p}, error={p} WHERE client_order_id={p}",
                    (order_id, status, error, client_order_id))
        conn.commit()
    finally:
        conn.close()


def update_investment(investment_id: str, status: str) -> None:
    _init()
    p = db._ph()
    conn = db._conn()
    try:
        cur = conn.cursor()
        cur.execute(f"UPDATE basket_investments SET status={p} WHERE id={p}", (status, investment_id))
        conn.commit()
    finally:
        conn.close()


def insert_fill(fill: dict) -> bool:
    _init()
    p = db._ph()
    conn = db._conn()
    try:
        cur = conn.cursor()
        verb = "INSERT INTO" if db._use_pg() else "INSERT OR IGNORE INTO"
        suffix = " ON CONFLICT (fill_id) DO NOTHING" if db._use_pg() else ""
        cur.execute(f"{verb} basket_fills VALUES ({','.join([p]*12)}){suffix}",
                    tuple(fill[k] for k in ("fill_id", "investment_id", "user_id", "basket_id",
                                            "order_id", "ticker", "side", "count", "price_dollars",
                                            "fee_dollars", "cost_dollars", "created_at")))
        inserted = cur.rowcount > 0
        conn.commit()
        return inserted
    finally:
        conn.close()


def get_baskets_stats(basket_ids: list[int]) -> dict[int, dict]:
    if not basket_ids:
        return {}
    p = db._ph()
    placeholders = ",".join([p] * len(basket_ids))
    rows = _many(f"SELECT basket_id, COUNT(DISTINCT user_id) AS investor_count, "
                 f"SUM(CAST(cost_dollars AS NUMERIC)) AS invested_dollars FROM basket_fills "
                 f"WHERE basket_id IN ({placeholders}) GROUP BY basket_id", basket_ids)
    result = {i: {"investor_count": 0, "invested_dollars": 0.0} for i in basket_ids}
    result.update({int(r["basket_id"]): {"investor_count": int(r["investor_count"]),
                                          "invested_dollars": round(float(r["invested_dollars"] or 0), 2)} for r in rows})
    return result


def get_basket_stats(basket_id: int) -> dict:
    return get_baskets_stats([basket_id])[basket_id]


def get_user_fills(user_id: str) -> list[dict]:
    p = db._ph()
    return _many(f"SELECT f.*, b.title AS basket_title FROM basket_fills f "
                 f"LEFT JOIN baskets b ON b.id=f.basket_id WHERE f.user_id={p} "
                 f"ORDER BY f.created_at DESC", (user_id,))


def get_user_orders(user_id: str) -> list[dict]:
    p = db._ph()
    return _many(f"SELECT o.*, b.title AS basket_title FROM basket_orders o "
                 f"LEFT JOIN baskets b ON b.id=o.basket_id WHERE o.user_id={p} "
                 f"ORDER BY o.created_at DESC", (user_id,))


def get_order_fills(order_id: str) -> list[dict]:
    p = db._ph()
    return _many(f"SELECT * FROM basket_fills WHERE order_id={p}", (order_id,))


def get_investment_by_preview(preview_id: str, user_id: str) -> dict | None:
    p = db._ph()
    return _one(f"SELECT * FROM basket_investments WHERE preview_id={p} AND user_id={p}",
                (preview_id, user_id))


def get_investment(investment_id: str) -> dict | None:
    p = db._ph()
    return _one(f"SELECT * FROM basket_investments WHERE id={p}", (investment_id,))


def get_investment_orders(investment_id: str) -> list[dict]:
    p = db._ph()
    return _many(f"SELECT * FROM basket_orders WHERE investment_id={p} ORDER BY created_at", (investment_id,))


def get_reconcilable_orders(user_id: str) -> list[dict]:
    p = db._ph()
    return _many(f"SELECT * FROM basket_orders WHERE user_id={p} AND status IN "
                 f"('submitting', 'submitted', 'pending_reconciliation') ORDER BY created_at DESC",
                 (user_id,))


def save_portfolio_snapshot(user_id: str, invested: float, current_value: float | None) -> None:
    _init()
    p = db._ph()
    conn = db._conn()
    try:
        cur = conn.cursor()
        day = datetime.now(timezone.utc).date().isoformat()
        cur.execute(f"DELETE FROM portfolio_snapshots WHERE user_id={p} AND snapshot_date={p}", (user_id, day))
        cur.execute(f"INSERT INTO portfolio_snapshots VALUES ({p},{p},{p},{p})",
                    (user_id, day, str(invested), None if current_value is None else str(current_value)))
        conn.commit()
    finally:
        conn.close()


def get_portfolio_history(user_id: str) -> list[dict]:
    p = db._ph()
    rows = _many(f"SELECT snapshot_date, invested_dollars, current_value_dollars FROM portfolio_snapshots "
                 f"WHERE user_id={p} ORDER BY snapshot_date", (user_id,))
    return [{"date": r["snapshot_date"], "invested_dollars": float(r["invested_dollars"]),
             "current_value_dollars": None if r["current_value_dollars"] is None else float(r["current_value_dollars"])}
            for r in rows]
