"""Assign the ten Prism-curated example baskets to named public profiles.

These are followable display profiles, not Supabase login identities. The basket
notes continue to say Prism selected the markets. Run with DATABASE_URL set;
the transaction checks every expected basket before changing any ownership.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path

import psycopg2


FIXTURE = Path(__file__).with_name("editorial_baskets_2026_10_16.json")
EDITORIAL_ID = "prism:editorial"
HANDLES = {
    "Andrew Schulz": "andrew_schulz",
    "David Villa": "david_villa",
    "J Balvin": "j_balvin",
    "Marcelo": "marcelo",
    "Marshawn Lynch": "marshawn_lynch",
    "Patrick Bet-David": "patrick_bet_david",
    "Rio Ferdinand": "rio_ferdinand",
    "Timothée Chalamet": "timothee_chalamet",
}


def profile_id(handle: str) -> str:
    return f"prism:curated:{handle}"


def assign(database_url: str, dry_run: bool = False) -> list[tuple[int, str, str]]:
    baskets = json.loads(FIXTURE.read_text())
    if len(baskets) != 10 or set(HANDLES) != {item["person"] for item in baskets}:
        raise RuntimeError("Editorial fixture or person mapping changed; review before assigning")
    conn = psycopg2.connect(database_url)
    try:
        with conn:
            with conn.cursor() as cur:
                # The production API also applies these migrations on startup.
                cur.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS display_name TEXT")
                cur.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS profile_kind TEXT NOT NULL DEFAULT 'member'")
                plan = []
                for item in baskets:
                    person, handle = item["person"], HANDLES[item["person"]]
                    cur.execute("SELECT id, user_id, basket_json FROM baskets WHERE title=%s FOR UPDATE", (item["name"],))
                    matches = cur.fetchall()
                    if len(matches) != 1:
                        raise RuntimeError(f"Expected one basket named {item['name']!r}; found {len(matches)}")
                    basket_id, owner_id, payload = matches[0]
                    if owner_id not in (EDITORIAL_ID, profile_id(handle)):
                        raise RuntimeError(f"Basket {basket_id} has an unexpected owner")
                    metadata = json.loads(payload).get("editorial_hypothetical") or {}
                    if metadata.get("inspiration_person") != person:
                        raise RuntimeError(f"Basket {basket_id} does not match its person metadata")
                    plan.append((basket_id, person, handle))
                for person, handle in HANDLES.items():
                    cur.execute("SELECT user_id FROM profiles WHERE username=%s", (handle,))
                    existing = cur.fetchone()
                    if existing and existing[0] != profile_id(handle):
                        raise RuntimeError(f"Username {handle!r} already belongs to another account")
                if dry_run:
                    conn.rollback()
                    return plan
                domains = {item["person"]: item["domain"] for item in baskets}
                now = datetime.now(timezone.utc).isoformat()
                for person, handle in HANDLES.items():
                    cur.execute(
                        """INSERT INTO profiles
                           (user_id, username, created_at, display_name, profile_kind, bio, domain_tags)
                           VALUES (%s,%s,%s,%s,%s,%s,%s)
                           ON CONFLICT (user_id) DO UPDATE SET
                             display_name=EXCLUDED.display_name,
                             profile_kind=EXCLUDED.profile_kind,
                             bio=EXCLUDED.bio,
                             domain_tags=EXCLUDED.domain_tags""",
                        (profile_id(handle), handle, now, person, "curated", None,
                         json.dumps([domains[person], "Prism-curated concepts"])),
                    )
                for basket_id, _, handle in plan:
                    cur.execute(
                        "UPDATE baskets SET user_id=%s WHERE id=%s AND user_id IN (%s,%s)",
                        (profile_id(handle), basket_id, EDITORIAL_ID, profile_id(handle)),
                    )
                    if cur.rowcount != 1:
                        raise RuntimeError(f"Could not assign basket {basket_id}")
                cur.execute("SELECT COUNT(*) FROM baskets WHERE user_id=%s", (EDITORIAL_ID,))
                remaining = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM follows WHERE follower_id=%s OR following_id=%s",
                            (EDITORIAL_ID, EDITORIAL_ID))
                follows = cur.fetchone()[0]
                if remaining == 0 and follows == 0:
                    cur.execute("DELETE FROM profiles WHERE user_id=%s", (EDITORIAL_ID,))
                return plan
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")
    for basket_id, person, handle in assign(database_url, args.dry_run):
        print(f"{basket_id}: {person} (@{handle})")


if __name__ == "__main__":
    main()
