"""Replace the 18 Prism concept blurbs with short descriptions of their theses.

The source fixtures supply the text. This updates both the basket summary shown
by the API and the copy stored in basket_json for reuse. It does not change the
positions, ownership, profile disclosures, or original editorial audit notes.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import psycopg2


FIXTURES = (
    Path(__file__).with_name("editorial_baskets_2026_10_16.json"),
    Path(__file__).with_name("thought_leader_baskets_2026_10_17.json"),
)


def update(database_url: str, dry_run: bool = False) -> list[tuple[int, str, str, bool]]:
    items = [item for fixture in FIXTURES for item in json.loads(fixture.read_text())]
    if len(items) != 18 or len({item["name"] for item in items}) != len(items):
        raise RuntimeError("Expected 18 distinct curated basket titles")

    conn = psycopg2.connect(database_url)
    try:
        with conn:
            with conn.cursor() as cur:
                changes = []
                for item in items:
                    cur.execute(
                        "SELECT id, user_id, basket_json, is_public FROM baskets WHERE title=%s FOR UPDATE",
                        (item["name"],),
                    )
                    matches = cur.fetchall()
                    if len(matches) != 1:
                        raise RuntimeError(f"Expected one basket named {item['name']!r}; found {len(matches)}")
                    basket_id, owner_id, raw_payload, is_public = matches[0]
                    payload = json.loads(raw_payload)
                    metadata = payload.get("editorial_hypothetical") or {}
                    if not owner_id.startswith("prism:") or metadata.get("inspiration_person") != item["person"]:
                        raise RuntimeError(f"Basket {basket_id} is not the expected Prism concept")
                    summary = item.get("summary") or item["thesis"]
                    if not summary or "Prism editorial" in summary or "no endorsement" in summary:
                        raise RuntimeError(f"Basket {basket_id} needs a plain thesis summary")
                    payload["basket_summary"] = summary
                    changes.append((basket_id, item["name"], summary, bool(is_public)))
                    if not dry_run:
                        cur.execute(
                            "UPDATE baskets SET summary=%s, basket_json=%s WHERE id=%s",
                            (summary, json.dumps(payload, ensure_ascii=False), basket_id),
                        )
                if dry_run:
                    conn.rollback()
                return changes
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")
    for basket_id, title, summary, is_public in update(database_url, args.dry_run):
        print(f"{basket_id} ({'public' if is_public else 'retired'}): {title} — {summary}")


if __name__ == "__main__":
    main()
