"""Minimal OpenAI-compatible chat client (httpx, no vendor SDK — DESIGN D2)."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx

__all__ = ["LLMClient", "LLMError", "ToolCall", "Delta"]


class LLMError(Exception):
    """LLM endpoint failure (connection, auth, or protocol)."""


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON string as emitted by the model


@dataclass
class Delta:
    """One streamed step: text fragment and/or the finished tool calls."""

    text: str = ""
    tool_calls: list[ToolCall] | None = None


class LLMClient:
    """Talks to any /chat/completions endpoint (OpenAI, Ollama, vLLM, …)."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout_s: float = 120.0,
    ) -> None:
        self.base_url = (
            base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        ).rstrip("/")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.model = model or os.environ.get("DATACHARTER_MODEL", "gpt-4o-mini")
        self.timeout_s = timeout_s

    async def stream(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> AsyncIterator[Delta]:
        """Stream a completion, yielding text deltas and assembling tool calls."""
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "stream": True,
        }
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"

        pending: dict[int, dict[str, str]] = {}
        try:
            async with (
                httpx.AsyncClient(timeout=self.timeout_s) as client,
                client.stream(
                    "POST", f"{self.base_url}/chat/completions", json=payload, headers=headers
                ) as resp,
            ):
                if resp.status_code >= 400:
                    body = (await resp.aread()).decode("utf-8", "replace")[:500]
                    raise LLMError(f"LLM endpoint returned {resp.status_code}: {body}")
                async for line in resp.aiter_lines():
                    delta = _parse_sse_line(line, pending)
                    if delta is not None:
                        yield delta
        except httpx.HTTPError as exc:
            raise LLMError(f"Could not reach LLM at {self.base_url}: {exc}") from None

        if pending:
            calls = [
                ToolCall(id=c["id"], name=c["name"], arguments=c["arguments"])
                for c in pending.values()
                if c.get("name")
            ]
            if calls:
                yield Delta(tool_calls=calls)


def _parse_sse_line(line: str, pending: dict[int, dict[str, str]]) -> Delta | None:
    if not line.startswith("data:"):
        return None
    data = line[len("data:") :].strip()
    if not data or data == "[DONE]":
        return None
    try:
        chunk = json.loads(data)
    except json.JSONDecodeError:
        return None
    choices = chunk.get("choices") or [{}]
    delta = choices[0].get("delta") or {}

    text = delta.get("content") or ""
    for tc in delta.get("tool_calls") or []:
        idx = tc.get("index", 0)
        slot = pending.setdefault(idx, {"id": "", "name": "", "arguments": ""})
        if tc.get("id"):
            slot["id"] = tc["id"]
        fn = tc.get("function") or {}
        if fn.get("name"):
            slot["name"] = fn["name"]
        if fn.get("arguments"):
            slot["arguments"] += fn["arguments"]
    return Delta(text=text) if text else None
