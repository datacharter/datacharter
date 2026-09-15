"""MCP --guard: heuristic firewall in front of an upstream MCP server.

Not contract-grade masking. Emails and SSNs in tool text are replaced, canary
tokens are scanned, oversized payloads are truncated, and every tools/call is
written to the flight recorder. Upstream tool names pass through unchanged.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import AsyncIterator, Callable
from typing import Any, Protocol

from datacharter.agent.tools import MASKED

__all__ = ["GuardProxy", "StdioUpstream", "serve_guard", "DEFAULT_MAX_BYTES"]

DEFAULT_MAX_BYTES = 65536
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CANARY_BLOCK = (
    "Error: canary tripwire. Response withheld (see `datacharter audit`)."
)


class Upstream(Protocol):
    async def rpc(self, message: dict) -> dict | None: ...


class GuardProxy:
    """Forward MCP JSON-RPC. Inspect tools/call results before the client sees them."""

    def __init__(
        self,
        upstream: Upstream,
        *,
        recorder=None,
        canary=None,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> None:
        self._upstream = upstream
        self.recorder = recorder
        self.canary = canary
        self._max_bytes = max_bytes

    async def handle(self, message: dict) -> dict | None:
        if message.get("method") == "initialize" and self.recorder is not None:
            params = message.get("params") if isinstance(message.get("params"), dict) else {}
            self.recorder.start_session(
                "mcp-guard", client=(params or {}).get("clientInfo")
            )
        response = await self._upstream.rpc(message)
        if response is None:
            return None
        if message.get("method") == "tools/call":
            return self._filter_call(message, response)
        return response

    def _filter_call(self, message: dict, response: dict) -> dict:
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        name = str((params or {}).get("name") or "")
        arguments = json.dumps((params or {}).get("arguments") or {})
        body = json.loads(json.dumps(response, default=str))
        texts = _collect_texts(body)
        blob = "\n".join(texts)
        hit = self.canary.scan(blob) if self.canary is not None else None
        if hit is not None and self.recorder is not None:
            rec_a = getattr(self.recorder, "record_alarm", None)
            if rec_a is not None:
                rec_a(name, arguments, hit)
        if hit is not None and getattr(self.canary, "mode", "log") == "block":
            body = {
                "jsonrpc": body.get("jsonrpc", "2.0"),
                "id": body.get("id"),
                "result": {
                    "content": [{"type": "text", "text": _CANARY_BLOCK}],
                    "isError": True,
                },
            }
        else:
            _rewrite_texts(body, self._scrub)
            err = body.get("error")
            if isinstance(err, dict) and isinstance(err.get("message"), str):
                err["message"] = self._scrub(err["message"])
        seen = json.dumps(body.get("result") or body.get("error") or {}, default=str)
        if self.recorder is not None:
            self.recorder.record_access(name, arguments, seen)
        return body

    def _scrub(self, text: str) -> str:
        if self.canary is not None:
            for tok in self.canary.tokens:
                if tok:
                    text = text.replace(tok, MASKED)
        text = _EMAIL.sub(MASKED, text)
        text = _SSN.sub(MASKED, text)
        raw = text.encode()
        if len(raw) <= self._max_bytes:
            return text
        cut = raw[: self._max_bytes].decode("utf-8", errors="ignore")
        return cut + "\n[truncated by datacharter mcp --guard]"


class StdioUpstream:
    """JSON-RPC over a child process stdin/stdout."""

    def __init__(self, argv: list[str]) -> None:
        self._proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
            text=True,
            bufsize=1,
        )

    async def rpc(self, message: dict) -> dict | None:
        import asyncio

        if self._proc.stdin is None or self._proc.stdout is None:
            raise RuntimeError("upstream MCP process has no stdio")
        self._proc.stdin.write(json.dumps(message, default=str) + "\n")
        self._proc.stdin.flush()
        if "id" not in message:
            return None
        want = message["id"]
        loop = asyncio.get_running_loop()
        while True:
            line = await loop.run_in_executor(None, self._proc.stdout.readline)
            if line == "":
                raise RuntimeError("upstream MCP process closed stdout")
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(msg, dict) and msg.get("id") == want:
                return msg

    def close(self) -> None:
        if self._proc.poll() is not None:
            return
        self._proc.terminate()
        try:
            self._proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self._proc.kill()


async def serve_guard(
    proxy: GuardProxy,
    *,
    lines: AsyncIterator[str] | None = None,
    write: Callable[[str], None] | None = None,
) -> None:
    """Read client JSON-RPC lines, write filtered responses."""
    from datacharter.mcp.server import _error, _stdin_lines, _stdout_write

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
        if not isinstance(message, dict):
            write(json.dumps(_error(None, -32600, "Invalid Request")) + "\n")
            continue
        response = await proxy.handle(message)
        if response is not None:
            write(json.dumps(response, default=str) + "\n")


def _collect_texts(obj: Any) -> list[str]:
    out: list[str] = []

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            if item.get("type") == "text" and isinstance(item.get("text"), str):
                out.append(item["text"])
            if isinstance(item.get("message"), str) and "code" in item:
                out.append(item["message"])
            for value in item.values():
                walk(value)
        elif isinstance(item, list):
            for value in item:
                walk(value)

    walk(obj)
    return out


def _rewrite_texts(obj: Any, transform: Callable[[str], str]) -> None:
    if isinstance(obj, dict):
        if obj.get("type") == "text" and isinstance(obj.get("text"), str):
            obj["text"] = transform(obj["text"])
        for value in obj.values():
            _rewrite_texts(value, transform)
    elif isinstance(obj, list):
        for value in obj:
            _rewrite_texts(value, transform)
