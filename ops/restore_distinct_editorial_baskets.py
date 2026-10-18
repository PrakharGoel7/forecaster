"""Restore the nine older Prism baskets with themes distinct from the current set.

The overlapping Anthropic IPO basket (ID 40) stays retired. All selected
markets are checked against Kalshi again before any production change.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import psycopg2

from assign_editorial_profiles import HANDLES, profile_id
from publish_editorial_baskets import check_markets


FIXTURE = Path(__file__).with_name("editorial_baskets_2026_10_16.json")
RESTORE_IDS = {35, 36, 37, 38, 39, 41, 42, 43, 44}


def restore(database_url: str, dry_run: bool = False) -> list[tuple[int, str]]:
    items = json.loads(FIXTURE.read_text())
    if len(items) != 10:
        raise RuntimeError("The original curated basket fixture has changed")
    selected = [item for index, item in enumerate(items, start=35) if index in RESTORE_IDS]
    if len(selected) != 9:
        raise RuntimeError("Expected nine distinct-theme baskets")
    check_markets(selected)

    conn = psycopg2.connect(database_url)
    try:
        with conn:
            with conn.cursor() as cur:
                plan = []
                for basket_id, item in zip(sorted(RESTORE_IDS), selected):
                    cur.execute(
                        "SELECT title, user_id, basket_json FROM baskets WHERE id=%s FOR UPDATE",
                        (basket_id,),
                    )
                    row = cur.fetchone()
                    if row is None:
                        raise RuntimeError(f"Basket {basket_id} is missing")
                    title, owner_id, raw_payload = row
                    expected_owner = profile_id(HANDLES[item["person"]])
                    metadata = json.loads(raw_payload).get("editorial_hypothetical") or {}
                    if (title != item["name"] or owner_id != expected_owner or
                            metadata.get("inspiration_person") != item["person"]):
                        raise RuntimeError(f"Basket {basket_id} no longer matches its reviewed fixture")
                    plan.append((basket_id, title))
                cur.execute("SELECT is_public FROM baskets WHERE id=40")
                duplicate_theme = cur.fetchone()
                if duplicate_theme is None or duplicate_theme[0]:
                    raise RuntimeError("Overlapping IPO basket 40 must remain retired")
                if dry_run:
                    conn.rollback()
                    return plan
                for basket_id, _ in plan:
                    cur.execute("UPDATE baskets SET is_public=TRUE WHERE id=%s", (basket_id,))
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
    for basket_id, title in restore(database_url, args.dry_run):
        print(f"{basket_id}: {title}")


if __name__ == "__main__":
    main()
