"""Publish the reviewed hypothetical baskets under Prism's editorial profile.

Usage: DATABASE_URL=... python ops/publish_editorial_baskets.py [--dry-run]
Market data is fetched again immediately before any database write. Re-running
skips baskets already owned by the editorial profile.
"""

from __future__ import annotations

import argparse
import concurrent.futures
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from urllib.request import urlopen

import psycopg2


FIXTURE = Path(__file__).with_name("editorial_baskets_2026_10_16.json")
PROFILE_ID = "prism:editorial"
USERNAME = "prism_editorial"
MARKET_API = "https://api.elections.kalshi.com/trade-api/v2/markets/"


def fetch_market(ticker: str) -> dict:
    with urlopen(MARKET_API + ticker, timeout=20) as response:
        return json.load(response)["market"]


def check_markets(baskets: list[dict]) -> dict[str, dict]:
    tickers = sorted({row["ticker"] for basket in baskets for row in basket["rows"]})
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        markets = dict(zip(tickers, pool.map(fetch_market, tickers)))
    now = datetime.now(timezone.utc)
    for basket in baskets:
        assert 5 <= len(basket["rows"]) <= 10, basket["name"]
        assert sum(row["weight"] for row in basket["rows"]) == 100, basket["name"]
        for row in basket["rows"]:
            market = markets[row["ticker"]]
            side = row["side"].lower()
            close = datetime.fromisoformat(market["close_time"].replace("Z", "+00:00"))
            offer = float(market.get(f"{side}_ask_dollars") or 0)
            volume = float(market.get("volume_fp") or 0)
            if market["status"] != "active" or close <= now or offer <= 0 or volume <= 0:
                raise ValueError(f"Unavailable market: {row['ticker']} ({market['status']}, {offer}, {volume})")
    return markets


def publish(baskets: list[dict], markets: dict[str, dict], dry_run: bool) -> list[tuple[int | None, str]]:
    if dry_run:
        return [(None, basket["name"]) for basket in baskets]
    if not os.environ.get("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL is required")
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    published = []
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT user_id FROM profiles WHERE username = %s", (USERNAME,))
                existing = cur.fetchone()
                if existing and existing[0] != PROFILE_ID:
                    raise RuntimeError("Editorial username belongs to another profile")
                cur.execute(
                    """INSERT INTO profiles (user_id, username, created_at, bio, domain_tags)
                    VALUES (%s,%s,%s,%s,%s)
                    ON CONFLICT (user_id) DO UPDATE SET bio = EXCLUDED.bio, domain_tags = EXCLUDED.domain_tags""",
                    (PROFILE_ID, USERNAME, datetime.now(timezone.utc).isoformat(),
                     "Prism's own hypothetical market baskets. Named public figures are topic inspiration only; they did not author, approve, or endorse these positions.",
                     json.dumps(["Prism editorial", "Hypothetical concepts"])),
                )
                for basket in baskets:
                    title = basket["name"]
                    cur.execute("SELECT id FROM baskets WHERE user_id = %s AND title = %s", (PROFILE_ID, title))
                    old = cur.fetchone()
                    if old:
                        published.append((old[0], title))
                        continue
                    rows = basket["rows"]
                    notes = (
                        f"Prism editorial thought experiment inspired by {basket['person']}'s public work. "
                        f"{basket['fit']} {basket['person']} did not create, review, approve, or endorse "
                        "this basket or its positions. No trade has been placed. "
                        f"Topic source: {basket['tie']}\n\nReview risk: {basket['risk']}"
                    )
                    summary = f"Hypothetical Prism editorial concept inspired by {basket['person']} (no endorsement). {basket['thesis']}"
                    holdings = []
                    for row in rows:
                        market = markets[row["ticker"]]
                        side = row["side"].lower()
                        holdings.append({
                            "ticker": row["ticker"],
                            "event_ticker": market.get("event_ticker"),
                            "question": " — ".join(part for part in (market.get("title"), market.get("yes_sub_title")) if part) or row["ticker"],
                            "event_title": market.get("title") or "",
                            "market_price": float(market[f"{side}_ask_dollars"]),
                            "close_date": market.get("close_time"),
                            "side": row["side"],
                            "role": "direct",
                            "weight_dollars": row["weight"],
                            "rationale": row["rationale"],
                            "main_risk": basket["risk"],
                            "rules_summary": market.get("rules_primary") or "",
                        })
                    payload = {
                        "basket_title": title,
                        "basket_summary": summary,
                        "construction_notes": "Prism editorial thought experiment; no named person participated and no trade was placed.",
                        "editorial_hypothetical": {
                            "inspiration_person": basket["person"],
                            "source_url": basket["tie"],
                        },
                        "holdings": holdings,
                        "total_notional": 100.0,
                    }
                    belief = {
                        "core_belief": basket["thesis"],
                        "time_horizon": "See contract close dates",
                        "key_drivers": [],
                        "scope": basket["domain"],
                        "confidence_level": "low",
                        "supporting_reasoning": basket["fit"],
                        "current_context": "",
                        "resolution_target": basket["thesis"],
                        "timeframe_start": "now",
                        "timeframe_end": "See contract close dates",
                        "mechanism": "Editorial selection of active Kalshi markets",
                        "falsifiers": [],
                        "mode_used": "manual",
                    }
                    cur.execute(
                        """INSERT INTO baskets
                        (created_at,title,summary,core_belief,mode,time_horizon,timeframe_start,
                         timeframe_end,resolution_target,mechanism,scope,key_drivers_json,
                         belief_summary_json,analysis_json,basket_json,total_notional,
                         screened_count,is_public,user_id,thesis_notes)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        RETURNING id""",
                        (datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), title, summary,
                         basket["thesis"], "manual", "See contract close dates", "now",
                         "See contract close dates", basket["thesis"],
                         "Editorial market selection", basket["domain"], json.dumps([]),
                         json.dumps(belief), json.dumps({"affected_domains": [basket["domain"]]}),
                         json.dumps(payload), 100.0, len(holdings), True, PROFILE_ID, notes),
                    )
                    basket_id = cur.fetchone()[0]
                    for holding in holdings:
                        cur.execute(
                            """INSERT INTO basket_holdings
                            (basket_id,ticker,event_ticker,question,side,role,weight_dollars,
                             rationale,main_risk,market_price_at_create,close_date)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (basket_id, holding["ticker"], holding["event_ticker"],
                             holding["question"], holding["side"], holding["role"],
                             holding["weight_dollars"], holding["rationale"],
                             holding["main_risk"], holding["market_price"], holding["close_date"]),
                        )
                    published.append((basket_id, title))
    finally:
        conn.close()
    return published


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    baskets = json.loads(FIXTURE.read_text())
    markets = check_markets(baskets)
    for basket_id, title in publish(baskets, markets, args.dry_run):
        print(f"{basket_id if basket_id is not None else 'checked'}: {title}")


if __name__ == "__main__":
    main()
