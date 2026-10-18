"""Remove the visible demo_ prefix from Prism sample profile usernames.

The internal user IDs stay stable, preserving basket ownership, follows, and
watchlists. Run once against the linked production database; reruns are safe.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import psycopg2

from publish_demo_community_baskets import validate_fixture


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    baskets = json.loads(args.fixture.read_text())
    validate_fixture(baskets)
    if not os.environ.get("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL is required")

    expected = {
        f"prism:demo:{basket['profile_key']}": (basket["profile_key"], basket["username"])
        for basket in baskets
    }
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT user_id, username, profile_kind FROM profiles WHERE user_id = ANY(%s)",
                    (list(expected),),
                )
                profiles = {user_id: (username, kind) for user_id, username, kind in cur.fetchall()}
                if set(profiles) != set(expected):
                    raise RuntimeError(f"Expected {len(expected)} sample profiles; found {len(profiles)}")
                cur.execute(
                    "SELECT user_id, username FROM profiles WHERE username = ANY(%s)",
                    ([new for _, new in expected.values()],),
                )
                for user_id, username in cur.fetchall():
                    if expected.get(user_id, (None, None))[1] != username:
                        raise RuntimeError(f"Username {username!r} belongs to another profile")
                for user_id, (old_handle, new_handle) in expected.items():
                    current, kind = profiles[user_id]
                    if kind != "demo" or current not in (old_handle, new_handle):
                        raise RuntimeError(f"Unexpected sample profile state for {user_id!r}: {current!r}, {kind!r}")
                    if current == old_handle and not args.dry_run:
                        cur.execute(
                            "UPDATE profiles SET username = %s WHERE user_id = %s AND username = %s",
                            (new_handle, user_id, old_handle),
                        )
                        if cur.rowcount != 1:
                            raise RuntimeError(f"Username update failed for {user_id!r}")
                    print(f"{old_handle} → {new_handle}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
