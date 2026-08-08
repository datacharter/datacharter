"""The agent loop: stream text, execute tool calls, feed results back until done."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal

from datacharter.agent.cache import AnswerCache
from datacharter.agent.llm import LLMClient, LLMError
from datacharter.agent.tools import TOOL_SPECS, ToolBox

__all__ = ["Agent", "AgentConfig", "AgentEvent"]

MAX_TURNS = 8


def _sql_arg(arguments: str) -> str | None:
    try:
        return json.loads(arguments).get("sql")
    except (ValueError, TypeError, AttributeError):
        return None

SYSTEM_PROMPT = """\
You are DataCharter's data analyst. You answer questions about the user's data
by exploring the catalog and running read-only SQL through your tools.

Rules:
- Discover before querying: use list_tables / describe_table to learn the
  schema. Never guess column names.
- Use fully-qualified relation names exactly as list_tables reports them.
- Prefer certified metrics: check list_metrics and call query_metric when one
  matches, instead of writing the aggregate SQL yourself.
- Queries are read-only. Keep exploratory queries small with LIMIT.
- Some columns are PII and come back masked as •••; never claim to reveal them.
- When a result is best seen as a chart, end your answer with a fenced
  ```vega-lite block containing a valid Vega-Lite spec whose data.values you
  fill from your query results.
- Be concise. Show the SQL you ran.
"""


def build_system(guides: str) -> str:
    """The system prompt, with workspace guides appended when the contract has them."""
    if not guides:
        return SYSTEM_PROMPT
    return (
        SYSTEM_PROMPT
        + "\nWorkspace guides — context from the data owners. Follow it when writing queries:\n\n"
        + guides
    )


@dataclass
class AgentConfig:
    llm: LLMClient = field(default_factory=LLMClient)
    max_turns: int = MAX_TURNS
    cache: AnswerCache | None = None


@dataclass
class AgentEvent:
    kind: Literal["text", "tool_call", "tool_result", "error", "done"]
    text: str = ""
    tool: str = ""
    detail: str = ""
    #: For a query tool_call, the SQL the agent ran (so the UI can surface it).
    sql: str = ""


class Agent:
    """One conversational turn = many LLM/tool rounds until a final answer."""

    def __init__(self, tools: ToolBox, config: AgentConfig | None = None) -> None:
        self._tools = tools
        self._config = config or AgentConfig()

    async def run(
        self, question: str, history: list[dict[str, Any]] | None = None
    ) -> AsyncIterator[AgentEvent]:
        cache = self._config.cache
        if cache is not None and not history:
            async for event in self._try_cache(question, cache):
                yield event
                if event.kind == "done":
                    return

        system = build_system(getattr(self._tools, "guides", ""))
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        messages.extend(history or [])
        messages.append({"role": "user", "content": question})

        last_query_sql: str | None = None
        for _turn in range(self._config.max_turns):
            assistant_text = ""
            tool_calls = None
            try:
                async for delta in self._config.llm.stream(messages, TOOL_SPECS):
                    if delta.text:
                        assistant_text += delta.text
                        yield AgentEvent(kind="text", text=delta.text)
                    if delta.tool_calls:
                        tool_calls = delta.tool_calls
            except LLMError as exc:
                yield AgentEvent(kind="error", detail=str(exc))
                return

            if not tool_calls:
                if cache is not None and not history and last_query_sql:
                    cache.put(question, last_query_sql)
                yield AgentEvent(kind="done")
                return

            messages.append(
                {
                    "role": "assistant",
                    "content": assistant_text or None,
                    "tool_calls": [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {"name": c.name, "arguments": c.arguments},
                        }
                        for c in tool_calls
                    ],
                }
            )
            for call in tool_calls:
                call_sql = _sql_arg(call.arguments) if call.name == "query" else None
                yield AgentEvent(
                    kind="tool_call", tool=call.name, detail=call.arguments, sql=call_sql or ""
                )
                if call_sql:
                    last_query_sql = call_sql
                result = await self._tools.run(call.name, call.arguments)
                yield AgentEvent(kind="tool_result", tool=call.name, detail=result)
                messages.append(
                    {"role": "tool", "tool_call_id": call.id, "content": result}
                )

        yield AgentEvent(
            kind="error", detail=f"Stopped after {self._config.max_turns} tool rounds."
        )

    async def _try_cache(self, question: str, cache: AnswerCache) -> AsyncIterator[AgentEvent]:
        """Re-run a cached question's SQL on current data (skips the LLM); silent on miss."""
        sql = cache.get(question)
        if not sql:
            return
        args = json.dumps({"sql": sql})
        result = await self._tools.run("query", args)
        if result.startswith("Error:"):  # cached SQL no longer valid — fall back to the LLM
            return
        yield AgentEvent(kind="tool_call", tool="query", detail=args, sql=sql)
        yield AgentEvent(kind="tool_result", tool="query", detail=result)
        yield AgentEvent(kind="text", text="(re-ran your saved query on current data)")
        yield AgentEvent(kind="done")
