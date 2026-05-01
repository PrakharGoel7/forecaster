"""Agent 2 — Market Screener.

Reads the local events cache (populated by sync_events.py) and identifies
which events are relevant to the user's belief. Returns event_tickers only —
no API calls here. Real-time market details are fetched after screening.
"""
from __future__ import annotations
import json
import os
from pathlib import Path

from openai import OpenAI

CACHE_FILE = Path(__file__).parent.parent / "events_cache.json"

# Elections adds ~1,400 events (~28k tokens). Include only when the belief is election-related.
ELECTION_KEYWORDS = {
    "election", "vote", "voting", "ballot", "candidate", "primary", "runoff",
    "president", "senator", "governor", "congress", "parliament", "referendum",
    "poll", "polling", "democrat", "republican", "party",
}

SYSTEM_PROMPT = """You are a prediction market screener. You will be given:
1. A user's belief about the future
2. A domain-by-domain impact analysis showing direct AND indirect ramifications of the belief
3. A list of Kalshi prediction market events (event_ticker | title | subtitle | category)

Your job: use the domain analysis to identify every event that could be used to express or test the belief — including indirect and second/third-order connections.

The domain analysis is your map. If it says "oil-driven inflation → Fed less likely to cut", you should shortlist Fed rate events even if they don't mention Iran. If it says "defense spending rises", find defense legislation events.

Return 20-35 event_tickers. Err on the side of inclusion — the curator does final filtering.
Only return tickers that appear exactly in the provided list."""

_SCREEN_TOOL = {
    "type": "function",
    "function": {
        "name": "select_events",
        "description": "Return the event_tickers most relevant to the user's belief.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_tickers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "15-30 event_tickers from the provided list that are relevant to the belief.",
                },
                "reasoning": {
                    "type": "string",
                    "description": "One sentence explaining the screening logic.",
                },
            },
            "required": ["event_tickers", "reasoning"],
        },
    },
}


def _load_cache() -> list[dict]:
    if not CACHE_FILE.exists():
        raise FileNotFoundError(
            f"Event cache not found at {CACHE_FILE}. "
            "Run `python sync_events.py` first."
        )
    data = json.loads(CACHE_FILE.read_text())
    return data["events"]


def _format_events(events: list[dict]) -> str:
    lines = []
    for e in events:
        parts = [e["event_ticker"], e["title"]]
        if e.get("sub_title"):
            parts.append(e["sub_title"])
        parts.append(f"[{e['category']}]")
        lines.append(" | ".join(parts))
    return "\n".join(lines)


class ScreenerAgent:
    def __init__(self, api_key: str | None = None, model: str = "openai/gpt-4o"):
        self._client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key or os.environ["OPENROUTER_API_KEY"],
        )
        self._model = model

    def run(self, belief_summary: dict, analysis: dict | None = None) -> list[str]:
        all_events = _load_cache()

        # Include Elections only if the belief is explicitly election-related
        belief_words = set(
            (belief_summary.get("core_belief", "") + " " + belief_summary.get("scope", "")).lower().split()
        )
        include_elections = bool(belief_words & ELECTION_KEYWORDS)
        events = [
            e for e in all_events
            if e["category"] != "Elections" or include_elections
        ]

        if include_elections:
            print(f"  Including Elections category ({sum(1 for e in all_events if e['category'] == 'Elections')} events)")

        belief_text = (
            f"Belief: {belief_summary['core_belief']}\n"
            f"Time horizon: {belief_summary['time_horizon']}\n"
            f"Key drivers: {', '.join(belief_summary['key_drivers'])}\n"
            f"Scope: {belief_summary['scope']}"
        )

        if analysis:
            from agents.analyst_agent import AnalystAgent
            analysis_text = AnalystAgent().format_for_screener(analysis)
            belief_text = f"{belief_text}\n\n{analysis_text}"

        events_text = _format_events(events)

        prompt = f"{belief_text}\n\nAvailable events ({len(events)} total):\n{events_text}"

        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            tools=[_SCREEN_TOOL],
            tool_choice={"type": "function", "function": {"name": "select_events"}},
            max_tokens=1024,
        )

        tc = response.choices[0].message.tool_calls[0]
        result = json.loads(tc.function.arguments)

        # Validate — only return tickers that actually exist in the cache
        valid_tickers = {e["event_ticker"] for e in events}
        screened = [t for t in result["event_tickers"] if t in valid_tickers]

        print(f"  Screener reasoning: {result['reasoning']}")
        return screened
