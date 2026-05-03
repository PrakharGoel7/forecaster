"""Agent 1 — Belief Elicitor.

Conducts a short conversation to deeply understand the user's belief.
Before asking any follow-up questions the agent searches the web for
context so it never asks things it could look up (e.g. "when did the
Iran war start?"). Follow-up questions are reserved for things only the
user knows: their conviction, personal time horizon, and what would
change their mind.
"""
from __future__ import annotations
import json
import os

import httpx
from bs4 import BeautifulSoup
from ddgs import DDGS
from openai import OpenAI

def _make_system_prompt() -> str:
    from datetime import date
    today = date.today().strftime("%B %d, %Y")
    return f"""You are a sharp, well-read assistant helping someone articulate their belief about the future so they can find relevant prediction markets to bet on.

TODAY'S DATE: {today}
Your training data has a knowledge cutoff that may be over a year old. You MUST use web_search to learn the current state of affairs — do not rely on your own memory for recent events. Treat search results as ground truth.

WORKFLOW — follow this order strictly:
1. RESEARCH FIRST: Before asking the user anything, call web_search 1-2 times to learn what is happening RIGHT NOW related to their belief. Search for recent news (last few weeks/months). This prevents you from asking things you should already know (e.g. "when did it start?", "who is involved?") and ensures your questions reflect the current situation, not events from a year ago.
2. ASK INFORMED QUESTIONS: Ask 3 focused follow-up questions ONE AT A TIME. Questions should probe things only the user would know:
   - Their personal conviction and confidence level
   - What specific outcome or threshold they're predicting (be precise)
   - What would change their mind — what evidence would falsify their belief
   - Any nuance in their view that goes beyond the mainstream take
3. FINALIZE: After 3 exchanges, call finalize_belief.

Rules:
- Never ask something a quick web search would answer.
- Ask ONE question per reply. Keep it short and direct.
- Don't recap what you've found — just use it to ask better questions.
- Never call finalize_belief after fewer than 3 user replies."""

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current context, facts, and recent developments related to the user's belief. Call this BEFORE asking any questions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query — be specific and news-oriented.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finalize_belief",
            "description": "Call after 3 follow-up exchanges to lock in the structured belief summary.",
            "parameters": {
                "type": "object",
                "properties": {
                    "core_belief": {
                        "type": "string",
                        "description": "The user's core belief as one precise sentence.",
                    },
                    "time_horizon": {
                        "type": "string",
                        "description": "When the user expects this to happen.",
                    },
                    "key_drivers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "3-5 specific forces or trends the user believes are driving this.",
                    },
                    "scope": {
                        "type": "string",
                        "description": "Sectors, regions, or groups most impacted.",
                    },
                    "confidence_level": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": "The user's stated or implied confidence.",
                    },
                    "supporting_reasoning": {
                        "type": "string",
                        "description": "Key evidence or arguments the user offered.",
                    },
                    "current_context": {
                        "type": "string",
                        "description": "Brief summary of what you learned from web search about the current state of affairs.",
                    },
                },
                "required": [
                    "core_belief", "time_horizon", "key_drivers",
                    "scope", "confidence_level", "supporting_reasoning", "current_context",
                ],
            },
        },
    },
]


def _web_search(query: str, max_results: int = 4) -> list[dict]:
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return [
            {"title": r.get("title", ""), "snippet": r.get("body", ""), "url": r.get("href", "")}
            for r in results
        ]
    except Exception as e:
        return [{"error": str(e)}]


class BeliefAgent:
    def __init__(self, api_key: str | None = None, model: str = "openai/gpt-4o"):
        self._client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key or os.environ["OPENROUTER_API_KEY"],
        )
        self._model = model

    def step(self, history: list[dict], new_message: str) -> dict:
        """Single-turn step for web UI — stateless, history passed in and returned.

        Returns::
          { status: "asking"|"finalized", agent_message, search_queries, belief_summary, history }
        """
        msgs = list(history) + [{"role": "user", "content": new_message}]
        search_queries: list[str] = []

        while True:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "system", "content": _make_system_prompt()}] + msgs,
                tools=_TOOLS,
                max_tokens=400,
            )
            choice = response.choices[0]

            assistant_msg: dict = {"role": "assistant", "content": choice.message.content}
            if choice.message.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in choice.message.tool_calls
                ]
            msgs.append(assistant_msg)

            if choice.message.tool_calls:
                tool_results = []
                finalize_result = None

                for tc in choice.message.tool_calls:
                    args = json.loads(tc.function.arguments)
                    if tc.function.name == "web_search":
                        search_queries.append(args["query"])
                        results = _web_search(args["query"])
                        content = json.dumps(results)
                    elif tc.function.name == "finalize_belief":
                        finalize_result = args
                        content = json.dumps({"status": "finalized"})
                    else:
                        content = json.dumps({"error": f"unknown tool {tc.function.name}"})

                    tool_results.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": content,
                    })

                msgs.extend(tool_results)

                if finalize_result is not None:
                    return {
                        "status": "finalized",
                        "agent_message": None,
                        "search_queries": search_queries,
                        "belief_summary": finalize_result,
                        "history": msgs,
                    }
                continue

            return {
                "status": "asking",
                "agent_message": (choice.message.content or "").strip(),
                "search_queries": search_queries,
                "belief_summary": None,
                "history": msgs,
            }

    def run(self) -> dict:
        print("What's your belief about how the future will unfold?")
        print("(Could be about technology, geopolitics, economics, climate, markets — anything.)\n")
        initial = input("Your belief: ").strip()
        if not initial:
            raise ValueError("No belief provided.")

        messages: list[dict] = [{"role": "user", "content": initial}]
        user_reply_count = 0

        while True:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "system", "content": _make_system_prompt()}] + messages,
                tools=_TOOLS,
                max_tokens=400,
            )
            choice = response.choices[0]

            # Build assistant message to append to history
            assistant_msg: dict = {"role": "assistant", "content": choice.message.content}
            if choice.message.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in choice.message.tool_calls
                ]
            messages.append(assistant_msg)

            # Handle tool calls
            if choice.message.tool_calls:
                tool_results = []
                finalize_result = None

                for tc in choice.message.tool_calls:
                    args = json.loads(tc.function.arguments)

                    if tc.function.name == "web_search":
                        print(f"  [searching: {args['query']}]", flush=True)
                        results = _web_search(args["query"])
                        content = json.dumps(results)

                    elif tc.function.name == "finalize_belief":
                        finalize_result = args
                        content = json.dumps({"status": "finalized"})

                    else:
                        content = json.dumps({"error": f"unknown tool {tc.function.name}"})

                    tool_results.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": content,
                    })

                messages.extend(tool_results)

                if finalize_result is not None:
                    return finalize_result

                # After tool results, loop back to let the model continue
                continue

            # No tool call — model produced a conversational reply
            assistant_text = (choice.message.content or "").strip()
            if assistant_text:
                print(f"\nAssistant: {assistant_text}")
                user_reply = input("\nYou: ").strip()
                messages.append({"role": "user", "content": user_reply})
                user_reply_count += 1
