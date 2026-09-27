from __future__ import annotations

import os
import uuid
from pathlib import Path

_BASE_DIR = Path(__file__).parent
_CACHE_DIR = Path(os.environ.get("TRADING_COMPANION_CACHE_DIR", str(_BASE_DIR)))

EVENTS_CACHE_FILE = _CACHE_DIR / "events_cache.json"
EVENTS_CACHE_DB_FILE = _CACHE_DIR / "events_cache.db"
MARKETS_CACHE_FILE = _CACHE_DIR / "markets_cache.json"
MARKETS_CACHE_DB_FILE = _CACHE_DIR / "markets_cache.db"


def staging_path(target: Path) -> Path:
    """Return a unique staging path on the same filesystem as the target."""
    target.parent.mkdir(parents=True, exist_ok=True)
    return target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")


def remove_sqlite_sidecars(path: Path) -> None:
    """Remove WAL sidecars that must not be paired with a replacement DB."""
    for suffix in ("-wal", "-shm"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)


def publish_cache_pair(
    *,
    staged_json: Path,
    target_json: Path,
    staged_db: Path,
    target_db: Path,
) -> None:
    """Publish a fully built JSON/SQLite cache without exposing partial files."""
    remove_sqlite_sidecars(staged_db)
    remove_sqlite_sidecars(target_db)
    os.replace(staged_db, target_db)
    os.replace(staged_json, target_json)


def discard_staging_files(*paths: Path) -> None:
    for path in paths:
        path.unlink(missing_ok=True)
        remove_sqlite_sidecars(path)
