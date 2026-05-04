from __future__ import annotations

import os
from pathlib import Path

_BASE_DIR = Path(__file__).parent
_CACHE_DIR = Path(os.environ.get("TRADING_COMPANION_CACHE_DIR", str(_BASE_DIR)))

EVENTS_CACHE_FILE = _CACHE_DIR / "events_cache.json"
MARKETS_CACHE_FILE = _CACHE_DIR / "markets_cache.json"
