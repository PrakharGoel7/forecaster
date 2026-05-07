"""Agent 2 — Market Screener.

Reads the local events cache (populated by sync_events.py) and identifies
which events are relevant to the user's belief. Returns event_tickers only —
no API calls here. Real-time market details are fetched after screening.
"""
from __future__ import annotations
import json
import os

from openai import OpenAI
from cache_paths import EVENTS_CACHE_FILE
from event_cache_db import load_all_events, search_events_fts

CACHE_FILE = EVENTS_CACHE_FILE

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
    return load_all_events()


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
        baseline_events = [
            e for e in all_events
            if e["category"] != "Elections" or include_elections
        ]
        search_text = " ".join(
            part for part in [
                belief_summary.get("core_belief", ""),
                belief_summary.get("scope", ""),
                belief_summary.get("resolution_target", ""),
                belief_summary.get("mechanism", ""),
                " ".join(belief_summary.get("key_drivers", [])),
                " ".join(belief_summary.get("falsifiers", [])),
            ]
            if part
        )
        fts_events = search_events_fts(search_text, limit=1200)
        events = [
            e for e in fts_events
            if e["category"] != "Elections" or include_elections
        ] if fts_events else baseline_events
        if len(events) < 200:
            events = baseline_events

        if include_elections:
            print(f"  Including Elections category ({sum(1 for e in all_events if e['category'] == 'Elections')} events)")
        if fts_events:
            print(f"  FTS prefilter: {len(events)} candidate events from cached index")

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


MARKET_SCREENER_PROMPT = """You are evaluating retrieved contract-level candidate markets.

Your job is not to search. Your job is to select the best available markets, reject truly weak markets, choose the correct YES/NO side, and label proxy quality honestly.

Prefer clean/direct markets, but if direct markets are sparse, select useful proxies and label them clearly. Do not pretend a proxy is direct.

Rules:
- Reject overall_score below 2.5.
- Select 8–25 markets if available.
- Return fewer only if quality is truly thin.
- Prefer direct_thesis and mechanism markets.
- Markets with score 2.5–3.2 can be selected if direct/good markets are insufficient or if they add a useful early signal or hedge.
- Every selected partial_proxy or early_signal must include fit_warning.
- Recommended side must profit if the user's belief is true.
- Do not include absurdly broad markets unless clearly labeled and capped.
- At least 50% of selected markets should be direct_thesis, mechanism, strong_proxy, or good_proxy if available.

Scoring formula:
overall_score =
0.35 * expressiveness_score +
0.25 * resolution_fit_score +
0.20 * causal_purity_score +
0.15 * timeframe_alignment_score +
0.05 * liquidity_usability_score"""

_MARKET_SCREEN_TOOL = {
    "type": "function",
    "function": {
        "name": "select_markets",
        "description": "Select the strongest contract-level markets for the user's belief.",
        "parameters": {
            "type": "object",
            "properties": {
                "selected_markets": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "ticker": {"type": "string"},
                            "event_ticker": {"type": "string"},
                            "question": {"type": "string"},
                            "linked_exposure_name": {"type": "string"},
                            "route_ring": {
                                "type": "string",
                                "enum": ["direct", "strong_proxy", "early_signal"],
                            },
                            "tier": {
                                "type": "string",
                                "enum": ["direct_thesis", "mechanism", "first_order_consequence", "hedge_or_falsifier"],
                            },
                            "recommended_side": {"type": "string", "enum": ["YES", "NO"]},
                            "expressiveness_score": {"type": "number"},
                            "resolution_fit_score": {"type": "number"},
                            "causal_purity_score": {"type": "number"},
                            "timeframe_alignment_score": {"type": "number"},
                            "liquidity_usability_score": {"type": "number"},
                            "overall_score": {"type": "number"},
                            "fit_type": {
                                "type": "string",
                                "enum": ["direct_thesis", "strong_proxy", "good_proxy", "partial_proxy", "early_signal", "hedge"],
                            },
                            "fit_confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                            "fit_warning": {"type": ["string", "null"]},
                            "proxy_reason": {"type": ["string", "null"]},
                            "rationale": {"type": "string"},
                            "main_confounder": {"type": "string"},
                        },
                        "required": [
                            "ticker", "event_ticker", "question", "linked_exposure_name", "route_ring", "tier",
                            "recommended_side", "expressiveness_score",
                            "resolution_fit_score", "causal_purity_score", "timeframe_alignment_score",
                            "liquidity_usability_score", "overall_score", "fit_type", "fit_confidence",
                            "fit_warning", "proxy_reason", "rationale", "main_confounder",
                        ],
                    },
                },
                "coverage_summary": {
                    "type": "object",
                    "properties": {
                        "direct_count": {"type": "number"},
                        "strong_proxy_count": {"type": "number"},
                        "partial_proxy_count": {"type": "number"},
                        "early_signal_count": {"type": "number"},
                        "hedge_count": {"type": "number"},
                        "overall_coverage_quality": {
                            "type": "string",
                            "enum": ["direct", "strong_proxy", "mixed_proxy", "thin_market_coverage"],
                        },
                    },
                    "required": [
                        "direct_count", "strong_proxy_count", "partial_proxy_count",
                        "early_signal_count", "hedge_count", "overall_coverage_quality",
                    ],
                },
            },
            "required": ["selected_markets", "coverage_summary"],
        },
    },
}


class MarketScreenerAgent:
    def __init__(self, api_key: str | None = None, model: str = "openai/gpt-4o"):
        self._client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key or os.environ["OPENROUTER_API_KEY"],
        )
        self._model = model

    def run(self, belief_summary: dict, exposures: list[dict], exposure_candidates: list[dict]) -> dict:
        exposure_lines = []
        for exposure in exposures:
            exposure_lines.append(
                f"- {exposure.get('exposure_name')} | ring={exposure.get('route_ring')} | tier={exposure.get('tier')} | dir={exposure.get('direction_if_belief_true')} | "
                f"purity={exposure.get('causal_purity_score')} | expr={exposure.get('expressiveness_score')} | "
                f"path={exposure.get('causal_path')}"
            )

        candidate_lines: list[str] = []
        for group in exposure_candidates:
            candidate_lines.append(f"\nExposure: {group.get('exposure_name')}")
            for cand in group.get("candidates", []):
                candidate_lines.append(
                    f"[{cand.get('ticker')}] {cand.get('question')} | event={cand.get('event_ticker')} | "
                    f"title={cand.get('event_title')} | category={cand.get('category')} | "
                    f"ring={cand.get('route_ring')} | yes={cand.get('yes_price')} | no={cand.get('no_price')} | vol={cand.get('volume')} | "
                    f"retrieval={cand.get('retrieval_score')} | reasons={'; '.join(cand.get('retrieval_reasons', [])[:3])}"
                )

        prompt = (
            f"Belief: {belief_summary.get('core_belief', '')}\n"
            f"Resolution target: {belief_summary.get('resolution_target', '')}\n"
            f"Belief direction: {belief_summary.get('belief_direction', '')}\n"
            f"Desired exposure: {belief_summary.get('desired_exposure', '')}\n"
            f"Timeframe: {belief_summary.get('timeframe_start', '')} → {belief_summary.get('timeframe_end', belief_summary.get('time_horizon', ''))}\n"
            f"Mechanism: {', '.join(belief_summary.get('mechanism', []))}\n"
            f"Falsifiers: {'; '.join(belief_summary.get('falsifiers', []))}\n\n"
            f"Exposure routes:\n" + "\n".join(exposure_lines) + "\n\n"
            f"Retrieved candidate markets:\n" + "\n".join(candidate_lines)
        )

        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": MARKET_SCREENER_PROMPT},
                {"role": "user", "content": prompt},
            ],
            tools=[_MARKET_SCREEN_TOOL],
            tool_choice={"type": "function", "function": {"name": "select_markets"}},
            max_tokens=2400,
        )

        tc = response.choices[0].message.tool_calls[0]
        result = json.loads(tc.function.arguments)
        validated: list[dict] = []
        candidate_entries: list[dict] = []
        valid_candidates: dict[str, dict] = {}
        for group in exposure_candidates:
            exposure = group.get("exposure", {})
            for cand in group.get("candidates", []):
                bundle = {"candidate": cand, "exposure": exposure}
                candidate_entries.append(bundle)
                valid_candidates[cand["ticker"]] = bundle
        for selected in result.get("selected_markets", []):
            bundle = valid_candidates.get(selected["ticker"])
            source = bundle["candidate"] if bundle else None
            if not source:
                continue
            selected["overall_score"] = round(
                0.35 * float(selected.get("expressiveness_score", 0)) +
                0.25 * float(selected.get("resolution_fit_score", 0)) +
                0.20 * float(selected.get("causal_purity_score", 0)) +
                0.15 * float(selected.get("timeframe_alignment_score", 0)) +
                0.05 * float(selected.get("liquidity_usability_score", 0)),
                2,
            )
            if selected["overall_score"] < 2.5:
                continue
            selected["alignment"] = "YES" if selected.get("recommended_side") == "YES" else "NO"
            if not selected.get("route_ring"):
                selected["route_ring"] = source.get("route_ring", "direct")
            if selected["overall_score"] < 3.2 and not selected.get("fit_warning"):
                selected["fit_warning"] = "Useful proxy, but weaker than a clean direct market."
            if selected.get("fit_type") in {"partial_proxy", "early_signal"} and not selected.get("fit_warning"):
                selected["fit_warning"] = "This is not a direct resolution of the thesis."
            validated.append(selected)

        def _timeframe_scores(reasons: list[str]) -> tuple[float, float]:
            if "timeframe_aligned" in reasons:
                return 4.5, 4.5
            if "earlier_than_thesis_but_signal" in reasons:
                return 3.0, 2.5
            if "slightly_beyond_thesis_window" in reasons:
                return 3.0, 3.0
            if "later_than_thesis_window" in reasons:
                return 2.5, 2.0
            return 2.5, 2.5

        def _liquidity_score_from_candidate(candidate: dict) -> float:
            volume = float(candidate.get("volume") or 0.0)
            if candidate.get("yes_price") is None:
                return 1.5
            if volume >= 5000:
                return 4.5
            if volume >= 500:
                return 3.5
            if volume > 0:
                return 2.5
            return 1.5

        def _fit_label(route_ring: str, tier: str, overall_score: float) -> tuple[str, str, str | None]:
            if tier == "hedge_or_falsifier":
                return "hedge", ("medium" if overall_score >= 3.2 else "low"), "This position mainly offsets or falsifies the thesis."
            if overall_score >= 4.0:
                if route_ring == "direct" and tier == "direct_thesis":
                    return "direct_thesis", "high", None
                return "strong_proxy", "high", "This closely tracks the thesis but does not literally resolve it."
            if overall_score >= 3.2:
                if route_ring == "direct":
                    return "strong_proxy", "medium", "This tests the mechanism or a close expression of the thesis."
                return "good_proxy", "medium", "This is a close proxy rather than the final thesis resolution."
            if route_ring == "early_signal":
                return "early_signal", "low", "This resolves earlier or more indirectly than the full thesis."
            return "partial_proxy", "low", "This is a broader proxy and the thesis is only one driver."

        selected_tickers = {m["ticker"] for m in validated}
        heuristic_candidates: list[dict] = []
        for bundle in candidate_entries:
            candidate = bundle["candidate"]
            exposure = bundle["exposure"] or {}
            if candidate["ticker"] in selected_tickers:
                continue
            route_ring = exposure.get("route_ring", candidate.get("route_ring", "direct"))
            expressiveness = float(exposure.get("expressiveness_score", 3))
            causal_purity = float(exposure.get("causal_purity_score", 3))
            resolution_fit, timeframe_alignment = _timeframe_scores(candidate.get("retrieval_reasons", []))
            liquidity = _liquidity_score_from_candidate(candidate)
            overall_score = round(
                0.35 * expressiveness +
                0.25 * resolution_fit +
                0.20 * causal_purity +
                0.15 * timeframe_alignment +
                0.05 * liquidity,
                2,
            )
            if overall_score < 2.5:
                continue
            fit_type, fit_confidence, fit_warning = _fit_label(route_ring, exposure.get("tier", "mechanism"), overall_score)
            heuristic_candidates.append({
                "ticker": candidate["ticker"],
                "event_ticker": candidate["event_ticker"],
                "question": candidate["question"],
                "linked_exposure_name": exposure.get("exposure_name", ""),
                "route_ring": route_ring,
                "tier": exposure.get("tier", "mechanism"),
                "recommended_side": "YES" if exposure.get("direction_if_belief_true", "YES") in {"YES", "UP"} else "NO",
                "alignment": "YES" if exposure.get("direction_if_belief_true", "YES") in {"YES", "UP"} else "NO",
                "expressiveness_score": expressiveness,
                "resolution_fit_score": resolution_fit,
                "causal_purity_score": causal_purity,
                "timeframe_alignment_score": timeframe_alignment,
                "liquidity_usability_score": liquidity,
                "overall_score": overall_score,
                "fit_type": fit_type,
                "fit_confidence": fit_confidence,
                "fit_warning": fit_warning,
                "proxy_reason": None if route_ring == "direct" else exposure.get("why_this_is_clean_or_useful"),
                "rationale": exposure.get("why_this_is_clean_or_useful") or exposure.get("causal_path", ""),
                "main_confounder": "; ".join(exposure.get("main_confounders", [])[:2]),
            })

        heuristic_candidates.sort(key=lambda item: (-item["overall_score"], item["ticker"]))
        target_count = 8
        for candidate in heuristic_candidates:
            if len(validated) >= target_count and validated:
                break
            if candidate["ticker"] in selected_tickers:
                continue
            validated.append(candidate)
            selected_tickers.add(candidate["ticker"])
        coverage_summary = result.get("coverage_summary", {})
        if not coverage_summary:
            direct_count = sum(1 for m in validated if m.get("fit_type") == "direct_thesis")
            strong_proxy_count = sum(1 for m in validated if m.get("fit_type") in {"strong_proxy", "good_proxy"})
            partial_proxy_count = sum(1 for m in validated if m.get("fit_type") == "partial_proxy")
            early_signal_count = sum(1 for m in validated if m.get("fit_type") == "early_signal")
            hedge_count = sum(1 for m in validated if m.get("fit_type") == "hedge")
            overall_coverage_quality = (
                "direct" if direct_count >= max(2, len(validated) // 2) else
                "strong_proxy" if direct_count + strong_proxy_count >= max(3, len(validated) // 2) else
                "mixed_proxy" if validated else
                "thin_market_coverage"
            )
            coverage_summary = {
                "direct_count": direct_count,
                "strong_proxy_count": strong_proxy_count,
                "partial_proxy_count": partial_proxy_count,
                "early_signal_count": early_signal_count,
                "hedge_count": hedge_count,
                "overall_coverage_quality": overall_coverage_quality,
            }
        return {"selected_markets": validated, "coverage_summary": coverage_summary}
