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

SYSTEM_PROMPT = """You are a prediction market screener. Your job is to find markets that provide meaningful tradable exposure to a user's belief about the future.

You will receive:
1. A structured user belief with resolution_target and timeframe
2. A domain impact map showing which domains give clean exposure to the belief (keep_for_market_search=True) with causal distance and expressiveness scores
3. A list of Kalshi events

Select events only if they meaningfully express, test, or hedge the user's belief.

Classify every selected event into one of four tiers:
- direct_thesis: the market directly resolves the user's belief or resolution_target
- mechanism: the market tests the user's stated causal mechanism
- first_order_consequence: captures a likely immediate consequence of the belief being true
- hedge_or_falsifier: captures something that would weaken or falsify the belief

Avoid:
- markets that are only thematically adjacent
- broad macro markets where the belief is only a minor driver
- unrelated political/geopolitical markets
- speculative third-order effects unless no stronger markets exist

For each selected event return:
- event_ticker
- tier
- alignment: YES or NO (does betting YES align with the user's belief?)
- expressiveness_score: 1-5 (how directly does this market express the thesis?)
- causal_purity_score: 1-5 (is the belief the main driver of this market's outcome?)
- timeframe_alignment_score: 1-5 (does the market resolve within the user's timeframe?)
- overall_score: 0.45 * expressiveness + 0.30 * causal_purity + 0.25 * timeframe_alignment
- rationale: one sentence explaining how this market expresses the belief
- main_confounder: the biggest reason this market might move for reasons unrelated to the belief

Selection rules:
- Prefer direct_thesis and mechanism markets.
- Include first_order_consequence markets only if causally tight (causal_purity >= 3).
- Include hedge_or_falsifier markets only if they test the user's stated falsifiers.
- Do not include speculative macro spillovers unless fewer than 8 stronger candidates exist.
- Return 12-25 events total.
- Never select an event with overall_score below 3.0.
- Only return tickers that appear exactly in the provided list."""

_SCREEN_TOOL = {
    "type": "function",
    "function": {
        "name": "select_events",
        "description": "Return scored, tiered candidates for the user's belief.",
        "parameters": {
            "type": "object",
            "properties": {
                "candidates": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "event_ticker": {"type": "string"},
                            "tier": {
                                "type": "string",
                                "enum": ["direct_thesis", "mechanism",
                                         "first_order_consequence", "hedge_or_falsifier"],
                            },
                            "alignment": {"type": "string", "enum": ["YES", "NO"]},
                            "expressiveness_score": {"type": "integer"},
                            "causal_purity_score": {"type": "integer"},
                            "timeframe_alignment_score": {"type": "integer"},
                            "overall_score": {"type": "number"},
                            "rationale": {"type": "string"},
                            "main_confounder": {"type": "string"},
                        },
                        "required": [
                            "event_ticker", "tier", "alignment",
                            "expressiveness_score", "causal_purity_score",
                            "timeframe_alignment_score", "overall_score",
                            "rationale", "main_confounder",
                        ],
                    },
                },
                "rejected_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Patterns of markets considered and rejected, e.g. 'generic Fed cut markets — belief is not about monetary policy'.",
                },
            },
            "required": ["candidates", "rejected_patterns"],
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

    def run(self, belief_summary: dict, analysis: dict | None = None) -> dict:
        all_events = _load_cache()

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

        resolution_target = belief_summary.get("resolution_target", "")
        timeframe_start = belief_summary.get("timeframe_start", "")
        timeframe_end = belief_summary.get("timeframe_end", belief_summary.get("time_horizon", ""))

        belief_text = (
            f"Belief: {belief_summary['core_belief']}\n"
            f"Resolution target: {resolution_target}\n"
            f"Timeframe: {timeframe_start} → {timeframe_end}\n"
            f"Key drivers: {', '.join(belief_summary.get('key_drivers', []))}\n"
            f"Mechanism: {belief_summary.get('mechanism', '')}\n"
            f"Falsifiers: {'; '.join(belief_summary.get('falsifiers', []))}\n"
            f"Scope: {belief_summary.get('scope', '')}"
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
            max_tokens=2048,
        )

        tc = response.choices[0].message.tool_calls[0]
        result = json.loads(tc.function.arguments)

        valid_tickers = {e["event_ticker"] for e in events}
        validated_candidates = []
        for c in result.get("candidates", []):
            if c["event_ticker"] not in valid_tickers:
                continue
            # Recalculate overall_score from components to ensure formula consistency
            c["overall_score"] = round(
                0.45 * c.get("expressiveness_score", 3) +
                0.30 * c.get("causal_purity_score", 3) +
                0.25 * c.get("timeframe_alignment_score", 3),
                2
            )
            validated_candidates.append(c)

        rejected_patterns = result.get("rejected_patterns", [])
        print(f"  Screener: {len(validated_candidates)} candidates, {len(rejected_patterns)} rejected patterns")
        return {"candidates": validated_candidates, "rejected_patterns": rejected_patterns}
