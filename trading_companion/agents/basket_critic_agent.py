"""Optional draft basket critic for deep mode."""
from __future__ import annotations

import json
import os

from openai import OpenAI

SYSTEM_PROMPT = """You are a prediction market basket critic.

Audit the draft basket before it is shown to the user.

Checks:
- Does every holding profit if the user's belief is true?
- Are any holdings merely thematic rather than causal?
- Are there duplicate exposures?
- Is timeframe aligned?
- Is the YES/NO side correct?
- Is the basket understandable to a retail user?
- Are confounders disclosed honestly?
- Are proxies labeled honestly?
- Are weak proxies overweighted?
- Are broad proxies capped?
- Is the basket_quality label accurate?
- Are fit_warnings present where needed?

Do not fail the basket just because proxies are included.
Return pass if the basket is coherent.
Return needs_repair if a clear fix exists.
Return fail only if holdings are unrelated, sides are wrong, duplicate exposure is severe, or proxy labeling is misleading."""

_CRITIC_TOOL = {
    "type": "function",
    "function": {
        "name": "critique_basket",
        "description": "Audit a draft basket and suggest repairs if needed.",
        "parameters": {
            "type": "object",
            "properties": {
                "verdict": {"type": "string", "enum": ["pass", "needs_repair", "fail"]},
                "issues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                            "holding_ticker": {"type": ["string", "null"]},
                            "issue": {"type": "string"},
                            "suggested_fix": {"type": "string"},
                        },
                        "required": ["severity", "holding_ticker", "issue", "suggested_fix"],
                    },
                },
                "suggested_removals": {"type": "array", "items": {"type": "string"}},
                "suggested_replacements": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "remove_ticker": {"type": "string"},
                            "add_ticker": {"type": "string"},
                            "reason": {"type": "string"},
                        },
                        "required": ["remove_ticker", "add_ticker", "reason"],
                    },
                },
                "final_notes": {"type": "string"},
            },
            "required": ["verdict", "issues", "suggested_removals", "suggested_replacements", "final_notes"],
        },
    },
}


class BasketCriticAgent:
    def __init__(self, api_key: str | None = None, model: str = "openai/gpt-4o"):
        self._client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key or os.environ["OPENROUTER_API_KEY"],
        )
        self._model = model

    def run(self, belief_summary: dict, exposures: list[dict], selected_markets: list[dict], draft_basket: dict) -> dict:
        prompt = (
            f"Belief: {belief_summary.get('core_belief', '')}\n"
            f"Resolution target: {belief_summary.get('resolution_target', '')}\n"
            f"Timeframe: {belief_summary.get('timeframe_start', '')} → {belief_summary.get('timeframe_end', belief_summary.get('time_horizon', ''))}\n\n"
            f"Exposure routes:\n{json.dumps(exposures[:12])}\n\n"
            f"Selected markets:\n{json.dumps(selected_markets[:25])}\n\n"
            f"Draft basket:\n{json.dumps(draft_basket)}"
        )

        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            tools=[_CRITIC_TOOL],
            tool_choice={"type": "function", "function": {"name": "critique_basket"}},
            max_tokens=1600,
        )
        tc = response.choices[0].message.tool_calls[0]
        return json.loads(tc.function.arguments)
