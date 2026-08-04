"""Minimal MCP server over stdio — exposes the governed query tools.

The four agent tools (list_sources / list_tables / describe_table / query) are
served as MCP tools. The read-only guard, PII masking, and error scrubbing are
inherited from `ToolBox` — the contract is the MCP surface, not reimplemented.

Transport: stdio, newline-delimited JSON-RPC 2.0 (MCP spec 2025-11-25). stdout
carries the protocol; all diagnostics go to stderr. Hand-rolled (no SDK) to keep
the dependency surface lean (D2), matching the hand-rolled OpenAI client.
"""

from __future__ import annotations

import json
import sys
from collections.abc import AsyncIterator, Callable
from typing import Any

from datacharter import __version__
from datacharter.agent.tools import TOOL_SPECS, ToolBox

__all__ = ["mcp_tool_defs", "handle_message", "serve_stdio"]

PROTOCOL_VERSION = "2025-11-25"
_SUPPORTED_VERSIONS = frozenset({"2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"})

# MCP tool annotations. Every tool is read-only (the ToolBox read-only guard rejects
# writes) and scoped to charter-declared sources — so readOnlyHint holds and the world
# is closed. Human-readable titles are surfaced by MCP clients and required by the
# Claude Connectors Directory.
_ANNOTATIONS: dict[str, dict[str, Any]] = {
    "list_sources": {"title": "List data sources"},
    "list_tables": {"title": "List tables"},
    "describe_table": {"title": "Describe table"},
    "query": {"title": "Run read-only SQL query"},
}
_READ_ONLY = {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False}


def mcp_tool_defs() -> list[dict[str, Any]]:
    """Adapt the OpenAI-shaped `TOOL_SPECS` to MCP tool definitions."""
    return [
        {
            "name": name,
            "title": _ANNOTATIONS[name]["title"],
            "description": spec["function"]["description"],
            "inputSchema": spec["function"]["parameters"],
            "annotations": {**_ANNOTATIONS[name], **_READ_ONLY},
        }
        for spec in TOOL_SPECS
        for name in [spec["function"]["name"]]
    ]


def _result(id_: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def _error(id_: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


async def handle_message(message: dict, toolbox: ToolBox) -> dict | None:
    """Dispatch one JSON-RPC message; return a response, or None for a notification."""
    if "id" not in message:  # a notification carries no id and takes no response
        return None
    id_ = message["id"]
    try:
        return await _dispatch(id_, message, toolbox)
    except Exception as exc:  # noqa: BLE001 — a handler error must not kill the stdio loop
        # Without this a raise in the canary scan or recorder tears down the
        # whole session with no JSON-RPC frame — the client just sees a dead pipe.
        return _error(id_, -32603, f"Internal error: {type(exc).__name__}")


async def _dispatch(id_: object, message: dict, toolbox: ToolBox) -> dict | None:
    method = message.get("method")

    if method == "initialize":
        params = message.get("params") or {}
        requested = params.get("protocolVersion")
        version = requested if requested in _SUPPORTED_VERSIONS else PROTOCOL_VERSION
        recorder = getattr(toolbox, "recorder", None)
        if recorder is not None:
            recorder.start_session("mcp", client=params.get("clientInfo"))
        # A proxy toolbox (`mcp --serve-url`) has no local recorder; ask the
        # serve process to open the session so accesses are attributed.
        remote_start = getattr(toolbox, "start_session", None)
        if remote_start is not None:
            await remote_start(params.get("clientInfo"))
        result = {
            "protocolVersion": version,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "datacharter", "version": __version__},
        }
        # Workspace guides ride the spec's `instructions` field so any MCP client
        # can inject the data owners' context into the model.
        guides = getattr(toolbox, "guides", "")
        if guides:
            result["instructions"] = guides
        return _result(id_, result)
    if method == "tools/list":
        return _result(id_, {"tools": mcp_tool_defs()})
    if method == "tools/call":
        params = message.get("params") or {}
        text = await toolbox.run(params.get("name", ""), json.dumps(params.get("arguments") or {}))
        return _result(
            id_,
            {"content": [{"type": "text", "text": text}], "isError": text.startswith("Error:")},
        )
    if method == "ping":
        return _result(id_, {})
    return _error(id_, -32601, f"Method not found: {method}")


async def serve_stdio(
    toolbox: ToolBox,
    *,
    lines: AsyncIterator[str] | None = None,
    write: Callable[[str], None] | None = None,
) -> None:
    """Read newline-delimited JSON-RPC (default stdin), write responses (default stdout)."""
    if lines is None:
        lines = _stdin_lines()
    if write is None:
        write = _stdout_write

    async for raw in lines:
        line = raw.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            write(json.dumps(_error(None, -32700, "Parse error")) + "\n")
            continue
        response = await handle_message(message, toolbox)
        if response is not None:
            write(json.dumps(response, default=str) + "\n")


async def _stdin_lines() -> AsyncIterator[str]:
    import asyncio

    loop = asyncio.get_event_loop()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if line == "":  # EOF — the client closed the pipe
            return
        yield line


def _stdout_write(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()
