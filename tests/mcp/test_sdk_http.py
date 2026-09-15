"""Official MCP SDK Streamable HTTP client against POST /mcp."""

import socket
import threading
import time

import httpx
import pytest
import uvicorn

from datacharter.cli import main as cli_main
from datacharter.server import create_app

mcp_sdk = pytest.importorskip("mcp", reason="official MCP SDK (dev extra) not installed")

from mcp.client.streamable_http import streamable_http_client  # noqa: E402

from mcp import ClientSession  # noqa: E402


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


@pytest.fixture
def mcp_url(tmp_path):
    assert cli_main(["init", str(tmp_path), "--demo"]) == 0
    app = create_app(tmp_path)
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 8
    while time.time() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=0.3).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.05)
    else:
        server.should_exit = True
        raise RuntimeError("MCP HTTP server did not start")
    try:
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        server.should_exit = True


async def test_sdk_streamable_http_initialize_list_and_query(mcp_url):
    async with streamable_http_client(mcp_url, terminate_on_close=False) as (
        read,
        write,
    ), ClientSession(read, write) as session:
        info = await session.initialize()
        assert info.server_info.name == "datacharter"
        tools = (await session.list_tools()).tools
        assert {t.name for t in tools} >= {"query", "list_tables"}
        result = await session.call_tool("query", {"sql": "SELECT 1 AS n"})
        text = "".join(c.text for c in result.content if hasattr(c, "text"))
        assert "1" in text
        assert result.is_error is not True
