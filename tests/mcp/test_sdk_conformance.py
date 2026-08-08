"""Conformance: the OFFICIAL MCP SDK client against our hand-rolled server.

`datacharter mcp` speaks JSON-RPC we wrote ourselves; every external client
(Claude Code, Claude Desktop, anything on the registry) speaks the SDK's
dialect. Passing our own tests proves nothing about theirs — this suite
connects with the real SDK over real stdio and exercises the full surface.
"""

import sys

import keyring
import keyring.backend
import pytest

from datacharter.cli import main as cli_main

mcp_sdk = pytest.importorskip("mcp", reason="official MCP SDK (dev extra) not installed")

from mcp.client.stdio import stdio_client  # noqa: E402

from mcp import ClientSession, StdioServerParameters  # noqa: E402


class _MemKeyring(keyring.backend.KeyringBackend):
    priority = 1

    def __init__(self):
        self.store = {}

    def get_password(self, s, n):
        return self.store.get((s, n))

    def set_password(self, s, n, v):
        self.store[(s, n)] = v

    def delete_password(self, s, n):
        self.store.pop((s, n), None)


@pytest.fixture
def ws(tmp_path):
    prev = keyring.get_keyring()
    keyring.set_keyring(_MemKeyring())
    assert cli_main(["init", str(tmp_path)]) == 0
    (tmp_path / "people.csv").write_text(
        "who,contact\nada,ada@example.com\ngrace,grace@example.com\nedsger,e@example.com\n"
    )
    (tmp_path / "charter.yaml").write_text(
        "version: 1\n"
        "sources:\n  people:\n    type: csv\n    path: people.csv\n"
        "metrics:\n  headcount:\n    relation: people\n    expression: count(*)\n"
    )
    yield tmp_path
    keyring.set_keyring(prev)


def _params(ws) -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable, args=["-m", "datacharter.cli", "mcp", str(ws)]
    )


async def test_sdk_initialize_and_list_tools(ws):
    async with stdio_client(_params(ws)) as (read, write), ClientSession(read, write) as session:  # noqa: E501
        info = await session.initialize()
        assert info.server_info.name
        tools = (await session.list_tools()).tools
        assert {t.name for t in tools} == {
            "query", "list_tables", "list_sources", "describe_table",
            "list_metrics", "query_metric",
        }
        for t in tools:
            # Schemas must be valid enough for a client to build calls from.
            assert t.description
            assert t.input_schema.get("type") == "object"


async def test_sdk_every_tool_call_round_trips(ws):
    async with stdio_client(_params(ws)) as (read, write), ClientSession(read, write) as session:  # noqa: E501
        await session.initialize()
        for name, args in [
            ("list_sources", {}),
            ("list_tables", {}),
            ("describe_table", {"relation": "people"}),
            ("query", {"sql": "SELECT count(*) AS n FROM people"}),
            ("list_metrics", {}),
            ("query_metric", {"name": "headcount"}),
        ]:
            result = await session.call_tool(name, args)
            assert result.content, name
            text = "".join(c.text for c in result.content if hasattr(c, "text"))
            assert text.strip(), name


async def test_sdk_sees_masked_pii_and_tool_errors(ws):
    async with stdio_client(_params(ws)) as (read, write), ClientSession(read, write) as session:  # noqa: E501
        await session.initialize()
        masked = await session.call_tool(
            "query", {"sql": "SELECT contact FROM people LIMIT 1"}
        )
        text = "".join(c.text for c in masked.content if hasattr(c, "text"))
        assert "ada@example.com" not in text
        # ••• may arrive JSON-escaped (\u2022) in the rendered payload.
        assert "•••" in text or "\\u2022\\u2022\\u2022" in text
        # Errors must come back as tool results a client can render,
        # not transport failures that kill the session.
        bad = await session.call_tool("query", {"sql": "SELECT nope FROM missing"})
        bad_text = "".join(c.text for c in bad.content if hasattr(c, "text"))
        assert "Error" in bad_text or bad.is_error
        # ...and the session must still be usable afterwards.
        again = await session.call_tool("query", {"sql": "SELECT 1 AS one"})
        assert "1" in "".join(c.text for c in again.content if hasattr(c, "text"))