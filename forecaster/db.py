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
            cur.execute("""
                CREATE TABLE IF NOT EXISTS profiles (
                    user_id    TEXT PRIMARY KEY,
                    username   TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS price_snapshots (
                    id            SERIAL PRIMARY KEY,
                    snapshot_date TEXT   NOT NULL,
                    ticker        TEXT   NOT NULL,
                    mid_price     REAL   NOT NULL,
                    UNIQUE (snapshot_date, ticker)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS follows (
                    follower_id   TEXT NOT NULL,
                    following_id  TEXT NOT NULL,
                    created_at    TEXT NOT NULL,
                    PRIMARY KEY (follower_id, following_id)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bookmarks (
                    user_id    TEXT    NOT NULL,
                    basket_id  INTEGER NOT NULL,
                    created_at TEXT    NOT NULL,
                    PRIMARY KEY (user_id, basket_id)
                )
            """)
            # Safe migrations for existing tables
            for stmt in [
                "ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS user_id TEXT",
                "ALTER TABLE baskets ADD COLUMN IF NOT EXISTS user_id TEXT",
                "ALTER TABLE baskets ADD COLUMN IF NOT EXISTS is_public BOOLEAN NOT NULL DEFAULT TRUE",
                "ALTER TABLE baskets ADD COLUMN IF NOT EXISTS thesis_notes TEXT",
                "ALTER TABLE baskets ADD COLUMN IF NOT EXISTS resolved_at TEXT",
                "ALTER TABLE baskets ADD COLUMN IF NOT EXISTS resolution_note TEXT",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS bio TEXT",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS domain_tags TEXT",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS twitter TEXT",
                "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS substack TEXT",
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
            cur.execute("""
                CREATE TABLE IF NOT EXISTS profiles (
                    user_id    TEXT PRIMARY KEY,
                    username   TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS price_snapshots (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    snapshot_date TEXT    NOT NULL,
                    ticker        TEXT    NOT NULL,
                    mid_price     REAL    NOT NULL,
                    UNIQUE (snapshot_date, ticker)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS follows (
                    follower_id   TEXT NOT NULL,
                    following_id  TEXT NOT NULL,
                    created_at    TEXT NOT NULL,
                    PRIMARY KEY (follower_id, following_id)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bookmarks (
                    user_id    TEXT    NOT NULL,
                    basket_id  INTEGER NOT NULL,
                    created_at TEXT    NOT NULL,
                    PRIMARY KEY (user_id, basket_id)
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
                "thesis_notes TEXT",
                "resolved_at TEXT",
                "resolution_note TEXT",
            ]:
                try:
                    cur.execute(f"ALTER TABLE baskets ADD COLUMN {col_def}")
                except Exception:
                    pass
            for col_def in ["bio TEXT", "domain_tags TEXT", "twitter TEXT", "substack TEXT"]:
                try:
                    cur.execute(f"ALTER TABLE profiles ADD COLUMN {col_def}")
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
                holdings, is_public: bool = True, user_id: str | None = None,
                thesis_notes: str | None = None) -> int:
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
            total_notional, screened_count, is_public, user_id, thesis_notes,
        )
        if _use_pg():
            cur.execute(f"""
                INSERT INTO baskets
                    (created_at, title, summary, core_belief, mode, time_horizon,
                     timeframe_start, timeframe_end, resolution_target, mechanism, scope,
                     key_drivers_json, belief_summary_json, analysis_json, basket_json,
                     total_notional, screened_count, is_public, user_id, thesis_notes)
                VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p})
                RETURNING id
            """, basket_values)
            basket_id = cur.fetchone()[0]
        else:
            cur.execute(f"""
                INSERT INTO baskets
                    (created_at, title, summary, core_belief, mode, time_horizon,
                     timeframe_start, timeframe_end, resolution_target, mechanism, scope,
                     key_drivers_json, belief_summary_json, analysis_json, basket_json,
                     total_notional, screened_count, is_public, user_id, thesis_notes)
                VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p})
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


def get_baskets(limit: int = 20, user_id: str | None = None, public_only: bool = False, by_username: str | None = None):
    _init()
    p = _ph()
    conn = _conn()
    try:
        cur = conn.cursor()
        clauses: list[str] = []
        params: list = []
        if by_username:
            clauses.append(f"p.username = {p}")
            params.append(by_username)
            clauses.append("b.is_public = 1" if not _use_pg() else "b.is_public = TRUE")
        elif user_id:
            clauses.append(f"b.user_id = {p}")
            params.append(user_id)
        elif public_only:
            clauses.append("b.is_public = 1" if not _use_pg() else "b.is_public = TRUE")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        cur.execute(
            f"SELECT b.*, p.username FROM baskets b LEFT JOIN profiles p ON b.user_id = p.user_id {where} ORDER BY b.created_at DESC LIMIT {p}",
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
            cur.execute(f"SELECT b.*, p.username FROM baskets b LEFT JOIN profiles p ON b.user_id = p.user_id WHERE b.id = {p} AND (b.user_id = {p} OR b.is_public = {'TRUE' if _use_pg() else '1'})", (basket_id, user_id))
        else:
            cur.execute(f"SELECT b.*, p.username FROM baskets b LEFT JOIN profiles p ON b.user_id = p.user_id WHERE b.id = {p} AND b.is_public = {'TRUE' if _use_pg() else '1'}", (basket_id,))
        row = cur.fetchone()
        if not row:
            return None
        basket = _rows_to_dicts([row], cur)[0]
        cur.execute(f"SELECT * FROM basket_holdings WHERE basket_id = {p} ORDER BY weight_dollars DESC, id ASC", (basket_id,))
        basket["holdings"] = _rows_to_dicts(cur.fetchall(), cur)
        return basket
    finally:
        conn.close()

def save_profile(user_id: str, username: str) -> dict:
    _init()
    p = _ph()
    conn = _conn()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        cur = conn.cursor()
        if _use_pg():
            cur.execute(
                f"INSERT INTO profiles (user_id, username, created_at) VALUES ({p},{p},{p}) "
                f"ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username",
                (user_id, username, ts),
            )
        else:
            cur.execute(
                f"INSERT INTO profiles (user_id, username, created_at) VALUES ({p},{p},{p}) "
                f"ON CONFLICT (user_id) DO UPDATE SET username = excluded.username",
                (user_id, username, ts),
            )
        conn.commit()
        return {"user_id": user_id, "username": username, "created_at": ts}
    finally:
        conn.close()


def _enrich_profile(profile: dict) -> dict:
    if profile and profile.get("domain_tags"):
        try:
            profile["domain_tags"] = json.loads(profile["domain_tags"])
        except Exception:
            profile["domain_tags"] = []
    counts = get_follow_counts(profile["user_id"]) if profile else {}
    profile.update(counts)
    profile["basket_count"] = _profile_basket_count(profile["user_id"])
    return profile


def _profile_basket_count(user_id: str) -> int:
    p = _ph()
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT COUNT(*) FROM baskets WHERE user_id = {p} AND is_public = {'TRUE' if _use_pg() else '1'}",
            (user_id,),
        )
        return cur.fetchone()[0]
    finally:
        conn.close()


def get_profile(user_id: str) -> dict | None:
    _init()
    p = _ph()
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM profiles WHERE user_id = {p}", (user_id,))
        row = cur.fetchone()
        if not row:
            return None
        return _enrich_profile(_rows_to_dicts([row], cur)[0])
    finally:
        conn.close()


def get_profile_by_username(username: str) -> dict | None:
    _init()
    p = _ph()
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM profiles WHERE username = {p}", (username,))
        row = cur.fetchone()
        if not row:
            return None
        return _enrich_profile(_rows_to_dicts([row], cur)[0])
    finally:
        conn.close()


def username_taken(username: str) -> bool:
    _init()
    p = _ph()
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT 1 FROM profiles WHERE username = {p}", (username,))
        return cur.fetchone() is not None
    finally:
        conn.close()


def update_basket_visibility(basket_id: int, user_id: str, is_public: bool) -> bool:
    _init()
    p = _ph()
    conn = _conn()
    try:
        cur = conn.cursor()
        val = is_public if _use_pg() else (1 if is_public else 0)
        cur.execute(
            f"UPDATE baskets SET is_public = {p} WHERE id = {p} AND user_id = {p}",
            (val, basket_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def save_price_snapshots(markets: list[dict], snapshot_date: str) -> int:
    """Archive daily mid_price for each ticker. Called by the nightly sync job."""
    if not markets:
        return 0
    _init()
    p = _ph()
    conn = _conn()
    count = 0
    try:
        cur = conn.cursor()
        for m in markets:
            ticker = m.get("ticker")
            mid = m.get("mid_price")
            if not ticker or mid is None:
                continue
            try:
                if _use_pg():
                    cur.execute(
                        f"INSERT INTO price_snapshots (snapshot_date, ticker, mid_price) "
                        f"VALUES ({p},{p},{p}) ON CONFLICT (snapshot_date, ticker) DO NOTHING",
                        (snapshot_date, ticker, float(mid)),
                    )
                else:
                    cur.execute(
                        f"INSERT OR IGNORE INTO price_snapshots (snapshot_date, ticker, mid_price) "
                        f"VALUES ({p},{p},{p})",
                        (snapshot_date, ticker, float(mid)),
                    )
                count += 1
            except Exception:
                pass
        conn.commit()
    finally:
        conn.close()
    return count


def update_profile(user_id: str, *, bio: str | None = None, domain_tags: list | None = None,
                   twitter: str | None = None, substack: str | None = None) -> dict | None:
    _init()
    p = _ph()
    conn = _conn()
    try:
        cur = conn.cursor()
        sets = []
        vals = []
        if bio is not None:
            sets.append(f"bio = {p}"); vals.append(bio)
        if domain_tags is not None:
            sets.append(f"domain_tags = {p}"); vals.append(json.dumps(domain_tags))
        if twitter is not None:
            sets.append(f"twitter = {p}"); vals.append(twitter)
        if substack is not None:
            sets.append(f"substack = {p}"); vals.append(substack)
        if not sets:
            return get_profile(user_id)
        vals.append(user_id)
        cur.execute(f"UPDATE profiles SET {', '.join(sets)} WHERE user_id = {p}", vals)
        conn.commit()
        return get_profile(user_id)
    finally:
        conn.close()


def follow_user(follower_id: str, following_id: str) -> bool:
    _init()
    p = _ph()
    conn = _conn()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        cur = conn.cursor()
        if _use_pg():
            cur.execute(
                f"INSERT INTO follows (follower_id, following_id, created_at) VALUES ({p},{p},{p}) "
                f"ON CONFLICT DO NOTHING",
                (follower_id, following_id, ts),
            )
        else:
            cur.execute(
                f"INSERT OR IGNORE INTO follows (follower_id, following_id, created_at) VALUES ({p},{p},{p})",
                (follower_id, following_id, ts),
            )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def unfollow_user(follower_id: str, following_id: str) -> bool:
    _init()
    p = _ph()
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(
            f"DELETE FROM follows WHERE follower_id = {p} AND following_id = {p}",
            (follower_id, following_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_follow_counts(user_id: str) -> dict:
    _init()
    p = _ph()
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM follows WHERE following_id = {p}", (user_id,))
        follower_count = cur.fetchone()[0]
        cur.execute(f"SELECT COUNT(*) FROM follows WHERE follower_id = {p}", (user_id,))
        following_count = cur.fetchone()[0]
        return {"follower_count": follower_count, "following_count": following_count}
    finally:
        conn.close()


def is_following(follower_id: str, following_id: str) -> bool:
    _init()
    p = _ph()
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT 1 FROM follows WHERE follower_id = {p} AND following_id = {p}",
            (follower_id, following_id),
        )
        return cur.fetchone() is not None
    finally:
        conn.close()


def get_feed(user_id: str, limit: int = 48) -> list[dict]:
    _init()
    p = _ph()
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT b.*, pr.username FROM baskets b "
            f"JOIN profiles pr ON b.user_id = pr.user_id "
            f"JOIN follows f ON f.following_id = b.user_id "
            f"WHERE f.follower_id = {p} AND b.is_public = {'TRUE' if _use_pg() else '1'} "
            f"ORDER BY b.created_at DESC LIMIT {p}",
            (user_id, limit),
        )
        return _rows_to_dicts(cur.fetchall(), cur)
    finally:
        conn.close()


def get_creators(limit: int = 50) -> list[dict]:
    """Return profiles sorted by follower count, enriched with basket and follower counts."""
    _init()
    p = _ph()
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT pr.*, "
            f"COUNT(DISTINCT f.follower_id) AS follower_count, "
            f"COUNT(DISTINCT b.id) AS basket_count "
            f"FROM profiles pr "
            f"LEFT JOIN follows f ON f.following_id = pr.user_id "
            f"LEFT JOIN baskets b ON b.user_id = pr.user_id AND b.is_public = {'TRUE' if _use_pg() else '1'} "
            f"GROUP BY pr.user_id "
            f"ORDER BY follower_count DESC, basket_count DESC "
            f"LIMIT {p}",
            (limit,),
        )
        rows = _rows_to_dicts(cur.fetchall(), cur)
        for r in rows:
            if r.get("domain_tags"):
                try:
                    r["domain_tags"] = json.loads(r["domain_tags"])
                except Exception:
                    r["domain_tags"] = []
        return rows
    finally:
        conn.close()


def bookmark_basket(user_id: str, basket_id: int) -> bool:
    _init()
    p = _ph()
    conn = _conn()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        cur = conn.cursor()
        if _use_pg():
            cur.execute(
                f"INSERT INTO bookmarks (user_id, basket_id, created_at) VALUES ({p},{p},{p}) "
                f"ON CONFLICT DO NOTHING",
                (user_id, basket_id, ts),
            )
        else:
            cur.execute(
                f"INSERT OR IGNORE INTO bookmarks (user_id, basket_id, created_at) VALUES ({p},{p},{p})",
                (user_id, basket_id, ts),
            )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def unbookmark_basket(user_id: str, basket_id: int) -> bool:
    _init()
    p = _ph()
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(
            f"DELETE FROM bookmarks WHERE user_id = {p} AND basket_id = {p}",
            (user_id, basket_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def is_bookmarked(user_id: str, basket_id: int) -> bool:
    _init()
    p = _ph()
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT 1 FROM bookmarks WHERE user_id = {p} AND basket_id = {p}",
            (user_id, basket_id),
        )
        return cur.fetchone() is not None
    finally:
        conn.close()


def get_bookmarks(user_id: str, limit: int = 48) -> list[dict]:
    _init()
    p = _ph()
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT b.*, pr.username FROM baskets b "
            f"JOIN bookmarks bk ON bk.basket_id = b.id "
            f"LEFT JOIN profiles pr ON b.user_id = pr.user_id "
            f"WHERE bk.user_id = {p} AND b.is_public = {'TRUE' if _use_pg() else '1'} "
            f"ORDER BY bk.created_at DESC LIMIT {p}",
            (user_id, limit),
        )
        return _rows_to_dicts(cur.fetchall(), cur)
    finally:
        conn.close()


def resolve_basket(basket_id: int, user_id: str, resolution_note: str) -> bool:
    _init()
    p = _ph()
    conn = _conn()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE baskets SET resolved_at = {p}, resolution_note = {p} "
            f"WHERE id = {p} AND user_id = {p}",
            (ts, resolution_note, basket_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_basket_performance(basket_id: int) -> dict:
    """Return a daily time-series of portfolio value indexed to 100 at creation.

    For each date we have price snapshots, computes a weighted portfolio value
    where 100 = break-even, >100 = gain, <100 = loss.
    """
    _init()
    p = _ph()
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT created_at FROM baskets WHERE id = {p}", (basket_id,))
        row = cur.fetchone()
        if not row:
            return {"dates": [], "values": [], "current_return": None}
        created_date = _rows_to_dicts([row], cur)[0]["created_at"][:10]

        cur.execute(
            f"SELECT ticker, side, weight_dollars, market_price_at_create "
            f"FROM basket_holdings WHERE basket_id = {p} AND market_price_at_create IS NOT NULL",
            (basket_id,),
        )
        holdings = _rows_to_dicts(cur.fetchall(), cur)
        if not holdings:
            return {"dates": [], "values": [], "current_return": None}

        tickers = [h["ticker"] for h in holdings]
        total_weight = sum(h["weight_dollars"] for h in holdings) or 1.0

        ph_list = ",".join([p] * len(tickers))
        cur.execute(
            f"SELECT snapshot_date, ticker, mid_price FROM price_snapshots "
            f"WHERE ticker IN ({ph_list}) AND snapshot_date >= {p} "
            f"ORDER BY snapshot_date ASC",
            (*tickers, created_date),
        )
        snapshot_rows = _rows_to_dicts(cur.fetchall(), cur)

        from collections import defaultdict
        by_date: dict[str, dict[str, float]] = defaultdict(dict)
        for r in snapshot_rows:
            by_date[r["snapshot_date"]][r["ticker"]] = r["mid_price"]

        dates = sorted(by_date.keys())
        values: list[float] = []
        for date in dates:
            prices = by_date[date]
            portfolio_value = 0.0
            covered_weight = 0.0
            for h in holdings:
                entry = h["market_price_at_create"]
                current = prices.get(h["ticker"])
                if current is None or not entry:
                    continue
                w = h["weight_dollars"] / total_weight
                if h["side"] == "YES":
                    portfolio_value += w * (current / entry)
                else:
                    entry_no = max(1.0 - entry, 0.001)
                    current_no = max(1.0 - current, 0.001)
                    portfolio_value += w * (current_no / entry_no)
                covered_weight += w
            if covered_weight > 0:
                values.append(round((portfolio_value / covered_weight) * 100, 2))

        current_return = round(values[-1] - 100.0, 2) if values else None
        return {"dates": dates, "values": values, "current_return": current_return}
    finally:
        conn.close()
