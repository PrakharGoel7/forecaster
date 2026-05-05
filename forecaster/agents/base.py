import json
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

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
    def __init__(self, config: ForecasterConfig, client_name: str = "llm"):
        self.config = config
        self.client_name = client_name
        self._client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=config.api_key,
            max_retries=3,
            default_headers={"X-Title": "Oracle Agentic Forecaster"},
        )
        self._call_index = 0

    def _log_path(self) -> Path:
        log_dir = Path(self.config.prompt_log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        date_dir = log_dir / datetime.now(timezone.utc).strftime("%Y-%m-%d")
        date_dir.mkdir(parents=True, exist_ok=True)
        return date_dir / f"{self.client_name}.jsonl"

    def _append_log(self, payload: dict) -> None:
        if not self.config.prompt_logging_enabled:
            return
        payload["logged_at"] = datetime.now(timezone.utc).isoformat()
        with self._log_path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=True, default=str) + "\n")

    def complete(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        force_tool: bool = False,
    ) -> NormalizedResponse:
        self._call_index += 1
        call_id = f"{self.client_name}-{self._call_index:03d}-{uuid4().hex[:8]}"
        started_at = datetime.now(timezone.utc)
        started_perf = perf_counter()
        kwargs: dict = dict(
            model=self.config.model,
            max_tokens=self.config.max_tokens_per_agent,
            messages=[{"role": "system", "content": system}] + messages,
            tools=[_to_openai_tool(t) for t in tools],
        )
        if force_tool:
            kwargs["tool_choice"] = "required"

        self._append_log({
            "phase": "request",
            "call_id": call_id,
            "client_name": self.client_name,
            "model": self.config.model,
            "force_tool": force_tool,
            "started_at": started_at.isoformat(),
            "system": system,
            "messages": messages,
            "tools": tools,
        })

        try:
            raw = self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            duration_ms = round((perf_counter() - started_perf) * 1000, 2)
            self._append_log({
                "phase": "error",
                "call_id": call_id,
                "client_name": self.client_name,
                "started_at": started_at.isoformat(),
                "duration_ms": duration_ms,
                "error_type": type(exc).__name__,
                "error": str(exc),
            })
            raise
        choice = raw.choices[0]
        duration_ms = round((perf_counter() - started_perf) * 1000, 2)

        tool_blocks = [
            ToolBlock(
                id=tc.id,
                name=tc.function.name,
                input=(
                    json.loads(tc.function.arguments)
                    if getattr(tc.function, "arguments", None)
                    else {}
                ),
            )
            for tc in (choice.message.tool_calls or [])
        ]
        self._append_log({
            "phase": "response",
            "call_id": call_id,
            "client_name": self.client_name,
            "started_at": started_at.isoformat(),
            "duration_ms": duration_ms,
            "assistant_text": choice.message.content,
            "tool_blocks": [{"id": tb.id, "name": tb.name, "input": tb.input} for tb in tool_blocks],
            "raw_response": raw.model_dump(mode="json"),
        })
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
        self._append_log({
            "phase": "tool_results",
            "client_name": self.client_name,
            "assistant_message": assistant_msg,
            "tool_results": tool_results,
        })
