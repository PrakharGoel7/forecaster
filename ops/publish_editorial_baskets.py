"""Publish Prism-curated hypothetical baskets through the ordinary thesis feed.

Usage: DATABASE_URL=... python ops/publish_editorial_baskets.py --fixture PATH [--retire-fixture PATH] [--dry-run]
Market data is fetched again immediately before any database write. Re-running
skips baskets already owned by the intended Prism-managed curated profile.
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
CURATED_HANDLES = {
    "Ray Dalio": "ray_dalio",
    "Nouriel Roubini": "nouriel_roubini",
    "Peter Zeihan": "peter_zeihan",
    "Scott Galloway": "scott_galloway",
    "Bill Gates": "bill_gates",
    "Mark Cuban": "mark_cuban",
    "Kara Swisher": "kara_swisher",
    "Andrew Yang": "andrew_yang",
    "José Alvarado": "jose_alvarado",
    "Luka Modrić": "luka_modric",
    "Bryson DeChambeau": "bryson_dechambeau",
}
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


def publish(baskets: list[dict], markets: dict[str, dict], dry_run: bool,
            retire_baskets: list[dict], curated_profiles: bool) -> list[tuple[int | None, str]]:
    if dry_run:
        return [(None, basket["name"]) for basket in baskets]
    if not os.environ.get("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL is required")
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    published = []
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS display_name TEXT")
                cur.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS profile_kind TEXT NOT NULL DEFAULT 'member'")
                for basket in baskets:
                    title = basket["name"]
                    person = basket["person"]
                    if curated_profiles:
                        handle = CURATED_HANDLES[person]
                        owner_id = f"prism:curated:{handle}"
                        bio = (f"Prism-managed profile. The baskets here are hypothetical concepts inspired by {person}'s public work. "
                               f"Prism selected the markets; {person} did not create, review, or endorse these positions.")
                        profile_kind, display_name = "curated", person
                    else:
                        handle, owner_id = USERNAME, PROFILE_ID
                        bio = "Prism's hypothetical market baskets. Named figures are topic inspiration only; they did not author, approve, or endorse these positions."
                        profile_kind, display_name = "member", "Prism editorial"
                    cur.execute("SELECT user_id FROM profiles WHERE username = %s", (handle,))
                    existing = cur.fetchone()
                    if existing and existing[0] != owner_id:
                        raise RuntimeError(f"Username {handle!r} belongs to another profile")
                    cur.execute(
                        """INSERT INTO profiles (user_id, username, created_at, display_name, profile_kind, bio, domain_tags)
                        VALUES (%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (user_id) DO UPDATE SET display_name=EXCLUDED.display_name,
                        profile_kind=EXCLUDED.profile_kind, bio=EXCLUDED.bio, domain_tags=EXCLUDED.domain_tags""",
                        (owner_id, handle, datetime.now(timezone.utc).isoformat(), display_name,
                         profile_kind, bio, json.dumps([basket["domain"], "Prism-curated concepts"])),
                    )
                    cur.execute("SELECT id, is_public FROM baskets WHERE user_id = %s AND title = %s", (owner_id, title))
                    old = cur.fetchone()
                    if old:
                        if not old[1]:
                            cur.execute("UPDATE baskets SET is_public=TRUE WHERE id=%s", (old[0],))
                        published.append((old[0], title))
                        continue
                    rows = basket["rows"]
                    notes = (
                        f"Prism editorial thought experiment inspired by {basket['person']}'s public work. "
                        f"{basket['fit']} {basket['person']} did not create, review, approve, or endorse "
                        "this basket or its positions. No trade has been placed. "
                        f"Topic source: {basket['tie']}\n\nReview risk: {basket['risk']}"
                    )
                    summary = basket.get("summary") or basket["thesis"]
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
                         json.dumps(payload), 100.0, len(holdings), True, owner_id, notes),
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
                for old_basket in retire_baskets:
                    cur.execute("SELECT id, user_id, basket_json FROM baskets WHERE title=%s FOR UPDATE", (old_basket["name"],))
                    matches = cur.fetchall()
                    if len(matches) != 1:
                        raise RuntimeError(f"Expected one old basket named {old_basket['name']!r}; found {len(matches)}")
                    basket_id, owner_id, raw_payload = matches[0]
                    metadata = json.loads(raw_payload).get("editorial_hypothetical") or {}
                    if (metadata.get("inspiration_person") != old_basket["person"] or
                            not owner_id.startswith("prism:")):
                        raise RuntimeError(f"Old basket {basket_id} no longer matches its Prism metadata")
                    cur.execute("UPDATE baskets SET is_public=FALSE WHERE id=%s", (basket_id,))
    finally:
        conn.close()
    return published


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    parser.add_argument("--retire-fixture", type=Path)
    parser.add_argument("--curated-profiles", action="store_true")
    args = parser.parse_args()
    baskets = json.loads(args.fixture.read_text())
    retire_baskets = json.loads(args.retire_fixture.read_text()) if args.retire_fixture else []
    if args.curated_profiles and {basket["person"] for basket in baskets} - set(CURATED_HANDLES):
        raise ValueError("A curated person is missing an approved Prism handle")
    if {basket["name"] for basket in baskets} & {basket["name"] for basket in retire_baskets}:
        raise ValueError("A new basket cannot also be retired")
    markets = check_markets(baskets)
    for basket_id, title in publish(baskets, markets, args.dry_run, retire_baskets, args.curated_profiles):
        print(f"{basket_id if basket_id is not None else 'checked'}: {title}")


if __name__ == "__main__":
    main()
