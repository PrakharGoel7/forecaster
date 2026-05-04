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
import re

import httpx
from bs4 import BeautifulSoup
from ddgs import DDGS
from openai import OpenAI

def _make_system_prompt() -> str:
    from datetime import date
    today = date.today().strftime("%B %d, %Y")
    return f"""You are an assistant helping a user express their belief about the future clearly enough to map it to relevant prediction markets.

TODAY'S DATE: {today}
Your training data has a knowledge cutoff that may be over a year old. You MUST use web_search to learn the current state of affairs — do not rely on your own memory for recent events. Treat search results as ground truth.

WORKFLOW

1. RESEARCH FIRST: Before asking the user anything, call web_search once to learn what is happening RIGHT NOW related to their belief. Search for recent news (last few weeks/months). This prevents you from asking things you should already know (e.g. "when did it start?", "who is involved?").

2. PARSE THE BELIEF
- Identify the core claim.
- Detect any ambiguous terms (e.g. “end”, “win”, “crash”, “soon”, “successful”, “replace”).
- If the belief is already clear and specific, DO NOT ask any questions → proceed to finalize.

3. ASK A SHORT CLARIFICATION RESPONSE (ONLY IF NEEDED)
- If the belief contains ambiguity in outcome or timeframe, ask a short clarification response.
- Focus ONLY on resolution clarity and timeframe.
- Ask 1 short question by default.
- If the user has not given a timeframe and a timeframe is important, you may ask 2 short questions in the SAME response:
  1. what counts as the belief being true
  2. when they expect it to happen
- Use the web research only for your own context. Do NOT explain the background, summarize recent news, justify the question, hedge with market expectations, or challenge the user's premise.
- Each question should usually be a single sentence under 20 words.

Examples:
- “Ukraine war will end soon” → “When you say ‘end’, do you mean a ceasefire, peace agreement, or reduced fighting?”
- “AI will replace programmers” → “What would count as ‘replace’ — majority of code written by AI, or widespread job loss?”
- “I think the Fed will cut rates” → “When do you think the Fed will cut rates?”
- “I think the Fed will cut interest rates” → “When do you think the Fed will cut rates? By how much?”

4. FINALIZE
- After either:
  a) zero questions (if already clear), OR
  b) one user response to your clarification, if that response resolves the ambiguity
→ call finalize_belief

- If ambiguity remains after the first reply, you may ask one more short follow-up question before finalizing.

RULES
- Ask as few questions as possible
- Ask at most 2 questions in a single response, and only when the second is needed to pin down timeframe
- Ask at most 2 total clarification turns before finalizing
- Keep responses extremely concise
- Never include research backstory in the user-facing question
- Never preface the question with context like “current context indicates”, “markets expect”, “despite”, or similar framing
- If you ask questions, output only the questions themselves"""

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
            "description": "Call when the belief is clear enough to lock in the structured belief summary, either immediately after web research if no clarification is needed or after one clarification response.",
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
                    "resolution_target": {
                        "type": "string",
                        "description": "The specific, observable outcome that would count as the belief being true.",
                    },
                    "resolution_type": {
                        "type": "string",
                        "enum": ["formal_resolution", "ceasefire", "meeting_or_negotiation", "policy_change",
                                 "price_move", "election_outcome", "other"],
                    },
                    "timeframe_start": {
                        "type": "string",
                        "description": "When this belief starts to be testable (e.g. 'now', 'Q3 2025').",
                    },
                    "timeframe_end": {
                        "type": "string",
                        "description": "Deadline by which the belief should resolve (e.g. 'end of 2025', 'within 6 months').",
                    },
                    "mechanism": {
                        "type": "string",
                        "description": "The user's stated causal mechanism — why they believe this will happen.",
                    },
                    "falsifiers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "2-3 pieces of evidence or events that would make the user doubt or abandon this belief.",
                    },
                },
                "required": [
                    "core_belief", "time_horizon", "key_drivers",
                    "scope", "confidence_level", "supporting_reasoning", "current_context",
                    "resolution_target", "resolution_type", "timeframe_start", "timeframe_end",
                    "mechanism", "falsifiers",
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


def _clean_question(text: str) -> str:
    text = " ".join((text or "").strip().split())
    if not text:
        return text

    # If the model leaked context, keep only the last one or two question-like sentences.
    question_spans = [m.group(0).strip() for m in re.finditer(r"[^?]*\?", text) if m.group(0).strip()]
    if question_spans:
        text = " ".join(question_spans[-2:]).strip()

    lower = text.lower()
    if "for example," in lower:
        text = re.split(r"\bfor example,\b", text, flags=re.IGNORECASE)[0].strip()
    if "for example:" in lower:
        text = re.split(r"\bfor example:\b", text, flags=re.IGNORECASE)[0].strip()

    # Remove common prefaces that turn the question into a mini-paragraph.
    prefixes = [
        "would you like to specify",
        "would you like to clarify",
        "do you want to specify",
        "do you want to clarify",
        "can you clarify",
        "could you clarify",
    ]
    for prefix in prefixes:
        if lower.startswith(prefix):
            if "when" in lower and ("what" in lower or "count" in lower):
                return "What exactly would count as this being true? When do you think this will happen?"
            if "when" in lower:
                return "When do you think this will happen?"
            return "What exactly would count as this being true?"

    words = text.split()
    if len(words) > 28:
        has_when = " when " in f" {lower} "
        has_what = " what " in f" {lower} " or " count " in f" {lower} "
        if has_when and has_what:
            return "What exactly would count as this being true? When do you think this will happen?"
        if has_when:
            return "When do you think this will happen?"
        if has_what:
            return "What exactly would count as this being true?"

    return text


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
                "agent_message": _clean_question((choice.message.content or "").strip()),
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
            assistant_text = _clean_question((choice.message.content or "").strip())
            if assistant_text:
                print(f"\nAssistant: {assistant_text}")
                user_reply = input("\nYou: ").strip()
                messages.append({"role": "user", "content": user_reply})
                user_reply_count += 1
