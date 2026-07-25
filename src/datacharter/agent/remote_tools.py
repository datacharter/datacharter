"""A ToolBox-shaped facade that forwards tool calls to a running `datacharter serve`.

Lets the stdio MCP server (`datacharter mcp --serve-url`) expose the governed tools without
opening a second engine, which would deadlock on the workspace state-DB lock. Governance is
the serve process's — `/api/tool` runs the same guarded, PII-masking toolbox as `/api/query`.
"""

from __future__ import annotations

import httpx


class RemoteToolBox:
    def __init__(
        self, serve_url: str, *, _transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._url = serve_url.rstrip("/") + "/api/tool"
        self._transport = _transport

    async def run(self, name: str, arguments: str) -> str:
        async with httpx.AsyncClient(transport=self._transport, timeout=120) as client:
            resp = await client.post(self._url, json={"name": name, "arguments": arguments or "{}"})
            resp.raise_for_status()
            return resp.json()["result"]
