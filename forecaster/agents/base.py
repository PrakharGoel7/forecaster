import json
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from forecaster.config import ForecasterConfig


@dataclass
class ToolBlock:
    id: str
    name: str
    input: dict


@dataclass
class NormalizedResponse:
    tool_blocks: list[ToolBlock] = field(default_factory=list)
    has_text: bool = False
    _raw: Any = field(default=None, repr=False)


def _to_openai_tool(tool: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool["input_schema"],
        },
    }


class LLMClient:
    def __init__(self, config: ForecasterConfig):
        self.config = config
        self._client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=config.api_key,
            max_retries=3,
            default_headers={"X-Title": "Oracle Agentic Forecaster"},
        )

    def complete(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        force_tool: bool = False,
    ) -> NormalizedResponse:
        kwargs: dict = dict(
            model=self.config.model,
            max_tokens=self.config.max_tokens_per_agent,
            messages=[{"role": "system", "content": system}] + messages,
            tools=[_to_openai_tool(t) for t in tools],
        )
        if force_tool:
            kwargs["tool_choice"] = "required"

        raw = self._client.chat.completions.create(**kwargs)
        choice = raw.choices[0]

        tool_blocks = [
            ToolBlock(id=tc.id, name=tc.function.name, input=json.loads(tc.function.arguments))
            for tc in (choice.message.tool_calls or [])
        ]
        return NormalizedResponse(tool_blocks=tool_blocks, has_text=bool(choice.message.content), _raw=raw)

    def extend_messages(
        self,
        messages: list[dict],
        response: NormalizedResponse,
        tool_results: list[dict],
    ) -> None:
        choice = response._raw.choices[0]
        assistant_msg: dict = {"role": "assistant", "content": choice.message.content}
        if choice.message.tool_calls:
            assistant_msg["tool_calls"] = [
                {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in choice.message.tool_calls
            ]
        messages.append(assistant_msg)
        for tr in tool_results:
            messages.append({"role": "tool", "tool_call_id": tr["tool_use_id"], "content": tr["content"]})
