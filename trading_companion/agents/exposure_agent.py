"""Tradable exposure route generator for the AI basket pipeline."""
from __future__ import annotations

import json
import os

from openai import OpenAI

SYSTEM_PROMPT = """You are a prediction-market exposure strategist.

Given a user's belief, produce tradable exposure routes: specific observable market outcomes that become more or less likely if the belief is true.

Do NOT list broad domains. Generate routes in three rings:
- Ring 1: direct / clean routes
- Ring 2: strong proxy routes
- Ring 3: early-signal / partial proxy routes

Prefer direct routes, but do not stop there. Generate enough routes so the downstream retrieval and screener can still build a useful basket when direct markets are sparse.

Each exposure route must:
- be a specific observable market outcome
- indicate the direction that profits if the belief is true
- identify the causal path from the belief to the exposure
- explain why the route is clean or, if a proxy, why it is still useful
- include search terms useful for Kalshi retrieval
- include negative search terms to filter thematic but wrong markets
- score causal purity and expressiveness

Rules:
- Return 8 to 18 exposure routes total.
- Include at least 3 direct/clean routes when possible.
- Include at least 3 strong proxy or early signal routes.
- Do not only generate perfect/direct routes.
- Include mechanism and first_order_consequence routes only when causally tight.
- Include hedge_or_falsifier routes only if useful and interpretable.
- Do not include absurdly broad or unrelated proxies.
- Every proxy route must explain why it is useful and what its main confounder is.
- Search terms should be market retrieval friendly, not essay phrases.
- Keep why_this_is_clean_or_useful concise and concrete."""

_EXPOSURE_TOOL = {
    "type": "function",
    "function": {
        "name": "map_exposures",
        "description": "Map a belief to specific tradable exposure routes.",
        "parameters": {
            "type": "object",
            "properties": {
                "exposures": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "exposure_name": {"type": "string"},
                            "route_ring": {
                                "type": "string",
                                "enum": ["direct", "strong_proxy", "early_signal"],
                            },
                            "tier": {
                                "type": "string",
                                "enum": ["direct_thesis", "mechanism", "first_order_consequence", "hedge_or_falsifier"],
                            },
                            "direction_if_belief_true": {
                                "type": "string",
                                "enum": ["YES", "NO", "UP", "DOWN"],
                            },
                            "causal_distance": {
                                "type": "string",
                                "enum": ["direct", "precursor", "first_order", "second_order", "speculative"],
                            },
                            "causal_path": {"type": "string"},
                            "why_this_is_clean_or_useful": {"type": "string"},
                            "main_confounders": {"type": "array", "items": {"type": "string"}},
                            "timeframe_fit": {
                                "type": "string",
                                "enum": ["strong", "partial", "weak"],
                            },
                            "search_terms": {"type": "array", "items": {"type": "string"}},
                            "negative_search_terms": {"type": "array", "items": {"type": "string"}},
                            "resolution_features": {"type": "array", "items": {"type": "string"}},
                            "causal_purity_score": {"type": "number"},
                            "expressiveness_score": {"type": "number"},
                        },
                        "required": [
                            "exposure_name", "route_ring", "tier", "direction_if_belief_true", "causal_distance",
                            "causal_path", "why_this_is_clean_or_useful", "main_confounders", "timeframe_fit",
                            "search_terms", "negative_search_terms", "resolution_features",
                            "causal_purity_score", "expressiveness_score",
                        ],
                    },
                },
                "rejected_routes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "route": {"type": "string"},
                            "reason": {"type": "string"},
                        },
                        "required": ["route", "reason"],
                    },
                },
            },
            "required": ["exposures", "rejected_routes"],
        },
    },
}


class ExposureAgent:
    def __init__(self, api_key: str | None = None, model: str = "openai/gpt-4o"):
        self._client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key or os.environ["OPENROUTER_API_KEY"],
        )
        self._model = model

    def run(self, belief_summary: dict) -> dict:
        prompt = (
            f"Core belief: {belief_summary.get('core_belief', '')}\n"
            f"Resolution target: {belief_summary.get('resolution_target', '')}\n"
            f"Belief direction: {belief_summary.get('belief_direction', '')}\n"
            f"Desired exposure: {belief_summary.get('desired_exposure', '')}\n"
            f"Timeframe: {belief_summary.get('timeframe_start', '')} → {belief_summary.get('timeframe_end', belief_summary.get('time_horizon', ''))}\n"
            f"Mechanism: {', '.join(belief_summary.get('mechanism', []))}\n"
            f"Key drivers: {', '.join(belief_summary.get('key_drivers', []))}\n"
            f"Falsifiers: {'; '.join(belief_summary.get('falsifiers', []))}\n"
            f"Scope: {belief_summary.get('scope', '')}\n"
            f"Confidence style: {belief_summary.get('confidence_style', '')}\n"
            f"Current context: {belief_summary.get('current_context', '')}"
        )

        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            tools=[_EXPOSURE_TOOL],
            tool_choice={"type": "function", "function": {"name": "map_exposures"}},
            max_tokens=2400,
        )

        tc = response.choices[0].message.tool_calls[0]
        return json.loads(tc.function.arguments)
