"""Publish Prism-created sample baskets under clearly labeled demo usernames.

Usage: DATABASE_URL=... python ops/publish_demo_community_baskets.py --fixture PATH [--dry-run]
The fixture is validated against live Kalshi market data before any database write.
Re-running the script keeps existing baskets and profiles rather than duplicating them.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re

import psycopg2

from publish_editorial_baskets import check_markets


def validate_fixture(baskets: list[dict]) -> None:
    if not baskets:
        raise ValueError("Fixture contains no baskets")
    names = [basket["name"] for basket in baskets]
    handles = [basket["username"] for basket in baskets]
    if len(names) != len(set(names)) or len(handles) != len(set(handles)):
        raise ValueError("Basket titles and demo usernames must be unique")
    for basket in baskets:
        handle = basket["username"]
        if not re.fullmatch(r"demo_[a-z0-9_]{3,19}", handle):
            raise ValueError(f"Invalid demo username: {handle}")
        rows = basket["rows"]
        if not 5 <= len(rows) <= 10:
            raise ValueError(f"Expected 5–10 markets: {basket['name']}")
        if len({row["ticker"] for row in rows}) != len(rows):
            raise ValueError(f"Duplicate market in {basket['name']}")
        if any(row["side"] not in ("YES", "NO") or row["weight"] <= 0 for row in rows):
            raise ValueError(f"Invalid side or weight in {basket['name']}")
        if sum(row["weight"] for row in rows) != 100:
            raise ValueError(f"Weights do not total 100 in {basket['name']}")


def publish(baskets: list[dict], markets: dict[str, dict], dry_run: bool) -> list[tuple[int | None, str]]:
    if dry_run:
        return [(None, basket["name"]) for basket in baskets]
    if not os.environ.get("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL is required")
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    published: list[tuple[int | None, str]] = []
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS display_name TEXT")
                cur.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS profile_kind TEXT NOT NULL DEFAULT 'member'")
                for basket in baskets:
                    handle = basket["username"]
                    owner_id = f"prism:demo:{handle}"
                    cur.execute("SELECT user_id FROM profiles WHERE username = %s", (handle,))
                    existing_profile = cur.fetchone()
                    if existing_profile and existing_profile[0] != owner_id:
                        raise RuntimeError(f"Username {handle!r} belongs to another profile")
                    now = datetime.now(timezone.utc)
                    bio = "Sample profile created by Prism. These market baskets were assembled by Prism; this is not a signed-up user or a record of trades."
                    cur.execute(
                        """INSERT INTO profiles
                        (user_id, username, created_at, display_name, profile_kind, bio, domain_tags)
                        VALUES (%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (user_id) DO UPDATE SET
                        profile_kind=EXCLUDED.profile_kind, bio=EXCLUDED.bio,
                        domain_tags=EXCLUDED.domain_tags""",
                        (owner_id, handle, now.isoformat(), None, "demo", bio,
                         json.dumps([basket["domain"]])),
                    )
                    cur.execute(
                        "SELECT id, is_public, basket_json FROM baskets WHERE user_id = %s AND title = %s",
                        (owner_id, basket["name"]),
                    )
                    existing_basket = cur.fetchone()
                    if existing_basket:
                        basket_id, is_public, old_payload = existing_basket
                        if (json.loads(old_payload).get("demo_basket") or {}).get("created_by") != "Prism":
                            raise RuntimeError(f"Basket {basket_id} is not a Prism sample")
                        if not is_public:
                            cur.execute("UPDATE baskets SET is_public = TRUE WHERE id = %s", (basket_id,))
                        published.append((basket_id, basket["name"]))
                        continue

                    holdings = []
                    for row in basket["rows"]:
                        market = markets[row["ticker"]]
                        side = row["side"].lower()
                        holdings.append({
                            "ticker": row["ticker"],
                            "event_ticker": market.get("event_ticker"),
                            "question": " — ".join(
                                part for part in (market.get("title"), market.get("yes_sub_title")) if part
                            ) or row["ticker"],
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
                        "basket_title": basket["name"],
                        "basket_summary": basket["summary"],
                        "construction_notes": "Prism-created sample on a synthetic profile; no person submitted these positions and no trade was placed.",
                        "demo_basket": {"created_by": "Prism"},
                        "holdings": holdings,
                        "total_notional": 100.0,
                    }
                    belief = {
                        "core_belief": basket["thesis"],
                        "time_horizon": "See contract close dates",
                        "key_drivers": [],
                        "scope": basket["domain"],
                        "confidence_level": "low",
                        "supporting_reasoning": "",
                        "current_context": "",
                        "resolution_target": basket["thesis"],
                        "timeframe_start": "now",
                        "timeframe_end": "See contract close dates",
                        "mechanism": "Prism-selected sample markets",
                        "falsifiers": [],
                        "mode_used": "manual",
                    }
                    notes = (
                        "Prism created this sample basket and synthetic profile. No person submitted these markets "
                        f"and no trade was placed.\n\nRisk: {basket['risk']}"
                    )
                    cur.execute(
                        """INSERT INTO baskets
                        (created_at,title,summary,core_belief,mode,time_horizon,timeframe_start,
                         timeframe_end,resolution_target,mechanism,scope,key_drivers_json,
                         belief_summary_json,analysis_json,basket_json,total_notional,
                         screened_count,is_public,user_id,thesis_notes)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        RETURNING id""",
                        (now.strftime("%Y-%m-%dT%H:%M:%SZ"), basket["name"], basket["summary"],
                         basket["thesis"], "manual", "See contract close dates", "now",
                         "See contract close dates", basket["thesis"], "Prism-selected sample markets",
                         basket["domain"], json.dumps([]), json.dumps(belief),
                         json.dumps({"affected_domains": [basket["domain"]]}), json.dumps(payload),
                         100.0, len(holdings), True, owner_id, notes),
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
                    published.append((basket_id, basket["name"]))
    finally:
        conn.close()
    return published


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    baskets = json.loads(args.fixture.read_text())
    validate_fixture(baskets)
    markets = check_markets(baskets, max_workers=2)
    for basket_id, title in publish(baskets, markets, args.dry_run):
        print(f"{basket_id if basket_id is not None else 'checked'}: {title}")


if __name__ == "__main__":
    main()
