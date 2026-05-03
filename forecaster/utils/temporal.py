"""Temporal grounding and source-reliability utilities."""
from datetime import datetime, timezone
from typing import Optional
import re

# ── Date helpers ──────────────────────────────────────────────────────────────

def current_date_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def current_year() -> int:
    return datetime.now(timezone.utc).year

def detect_stale_year_in_query(query: str) -> Optional[int]:
    """Return the oldest stale year referenced in a query, or None."""
    yr = current_year()
    years = [int(y) for y in re.findall(r'\b(20\d{2})\b', query)]
    stale = [y for y in years if y < yr - 1]
    return min(stale) if stale else None

def estimate_evidence_age(date_published: Optional[str]) -> str:
    if not date_published:
        return "stale"
    try:
        for fmt in ["%Y-%m-%d", "%Y-%m", "%Y"]:
            try:
                pub = datetime.strptime(date_published[:10].strip(), fmt)
                break
            except ValueError:
                continue
        else:
            return "stale"
        delta_days = (datetime.now() - pub).days
        if delta_days <= 90:
            return "current"
        elif delta_days <= 365:
            return "recent"
        return "stale"
    except Exception:
        return "stale"

# ── Source reliability ────────────────────────────────────────────────────────

_HIGH_DOMAINS = {
    "reuters.com", "apnews.com", "bloomberg.com", "ft.com", "wsj.com",
    "economist.com", "nytimes.com", "sec.gov", "federalreserve.gov",
    "bbc.com", "bbc.co.uk", "nature.com", "science.org", "arxiv.org",
    "pubmed.ncbi.nlm.nih.gov", "ssrn.com", "congress.gov", "whitehouse.gov",
    "supremecourt.gov", "imf.org", "worldbank.org", "bis.org",
    "ecb.europa.eu", "bls.gov", "census.gov", "cbo.gov", "cdc.gov", "nih.gov",
    "cmegroup.com", "cboe.com", "ice.com", "eurostat.ec.europa.eu",
    "fred.stlouisfed.org",
}

_LOW_DOMAINS = {
    "medium.com", "quora.com", "reddit.com", "seekingalpha.com",
    "motleyfool.com", "finbold.com", "cryptonews.com", "zerohedge.com",
    "x.com", "twitter.com", "t.co",
}

def score_source_reliability(url: str, source_title: str = "") -> str:
    url_lower = url.lower()
    for domain in _HIGH_DOMAINS:
        if domain in url_lower:
            return "high"
    if any(p in url_lower for p in [".gov/", ".gov\"", ".edu/", "/ir/",
                                     "/investor-relations/", "/investors/"]):
        return "high"
    for domain in _LOW_DOMAINS:
        if domain in url_lower:
            return "low"
    return "medium"
