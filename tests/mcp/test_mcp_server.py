import json

import pytest

from datacharter.agent.tools import MASKED, ToolBox
from datacharter.cli import main as cli_main
from datacharter.contracts import load_charter
from datacharter.engine.session import Engine
from datacharter.mcp.server import handle_message, mcp_tool_defs, serve_stdio


@pytest.fixture
def toolbox(tmp_path):
    cli_main(["init", str(tmp_path), "--demo"])
    charter = load_charter(tmp_path)
    eng = Engine(tmp_path, charter.sources).start()
    try:
        yield ToolBox(eng, charter.sources)
    finally:
        eng.close()


def _req(id_, method, params=None):
    msg = {"jsonrpc": "2.0", "id": id_, "method": method}
    if params is not None:
        msg["params"] = params
    return msg


def _call(id_, name, **arguments):
    return _req(id_, "tools/call", {"name": name, "arguments": arguments})


def test_tool_defs_are_mcp_shaped():
    defs = mcp_tool_defs()
    names = {d["name"] for d in defs}
    assert names == {"list_sources", "list_tables", "describe_table", "query"}
    for d in defs:
        assert set(d) >= {"name", "description", "inputSchema", "title", "annotations"}
        assert d["inputSchema"]["type"] == "object"
        # Directory requirement: a title and a read-only/destructive hint on every tool.
        assert d["title"]
        assert d["annotations"]["title"] == d["title"]
        assert d["annotations"]["readOnlyHint"] is True
    query = next(d for d in defs if d["name"] == "query")
    assert query["inputSchema"]["required"] == ["sql"]


async def test_initialize_handshake(toolbox):
    resp = await handle_message(
        _req(1, "initialize", {"protocolVersion": "2025-11-25", "capabilities": {}}), toolbox
    )
    assert resp["jsonrpc"] == "2.0" and resp["id"] == 1
    result = resp["result"]
    assert result["protocolVersion"] == "2025-11-25"
    assert "tools" in result["capabilities"]
    assert result["serverInfo"]["name"] == "datacharter"


async def test_initialize_defaults_version_when_unknown(toolbox):
    resp = await handle_message(
        _req(1, "initialize", {"protocolVersion": "1999-01-01"}), toolbox
    )
    assert resp["result"]["protocolVersion"] == "2025-11-25"


async def test_tools_list(toolbox):
    resp = await handle_message(_req(2, "tools/list"), toolbox)
    tools = resp["result"]["tools"]
    assert {t["name"] for t in tools} == {
        "list_sources",
        "list_tables",
        "describe_table",
        "query",
    }


async def test_tools_call_query_happy(toolbox):
    resp = await handle_message(
        _call(3, "query", sql="SELECT count(*) AS n FROM store.orders"), toolbox
    )
    result = resp["result"]
    assert result["isError"] is False
    payload = json.loads(result["content"][0]["text"])
    assert payload["rows"] == [[90]]


async def test_tools_call_write_is_error(toolbox):
    resp = await handle_message(_call(4, "query", sql="DELETE FROM store.customers"), toolbox)
    result = resp["result"]
    assert result["isError"] is True
    assert result["content"][0]["text"].startswith("Error:")


async def test_tools_call_masks_pii(toolbox):
    resp = await handle_message(_call(5, "query", sql="SELECT email FROM store.customers"), toolbox)
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["masked_columns"] == ["email"]
    assert all(row[0] == MASKED for row in payload["rows"])


async def test_unknown_method_is_jsonrpc_error(toolbox):
    resp = await handle_message(_req(6, "resources/list"), toolbox)
    assert resp["error"]["code"] == -32601
    assert "result" not in resp


async def test_notification_returns_none(toolbox):
    note = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    assert await handle_message(note, toolbox) is None


async def test_ping(toolbox):
    resp = await handle_message(_req(7, "ping"), toolbox)
    assert resp["result"] == {}


async def test_serve_stdio_loop_frames_one_json_per_line(toolbox):
    async def lines():
        yield json.dumps(_req(1, "initialize", {"protocolVersion": "2025-11-25"}))
        yield json.dumps(_req(2, "tools/list"))
        yield json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})

    out: list[str] = []
    await serve_stdio(toolbox, lines=lines(), write=out.append)

    assert len(out) == 2  # the notification produced no response
    for written in out:
        assert written.endswith("\n")
        assert "\n" not in written[:-1]  # no embedded newlines in the framed message
        json.loads(written)  # each line is a standalone JSON object


async def test_initialize_instructions_carry_guides(tmp_path):
    cli_main(["init", str(tmp_path), "--demo"])
    (tmp_path / "guides").mkdir(exist_ok=True)
    (tmp_path / "guides" / "overview.md").write_text("Exclude internal-tier customers.")
    charter = load_charter(tmp_path)
    eng = Engine(tmp_path, charter.sources).start()
    try:
        tb = ToolBox(eng, charter.sources, guides=charter.guides)
        resp = await handle_message(_req(1, "initialize", {"protocolVersion": "2025-11-25"}), tb)
        assert "Exclude internal-tier customers." in resp["result"]["instructions"]
    finally:
        eng.close()


async def test_initialize_omits_instructions_without_guides(toolbox):
    resp = await handle_message(_req(1, "initialize", {"protocolVersion": "2025-11-25"}), toolbox)
    assert "instructions" not in resp["result"]


async def test_initialize_records_client_attribution(tmp_path):
    from datacharter.audit import FlightRecorder
    from datacharter.audit.evidence import read_entries

    cli_main(["init", str(tmp_path), "--demo"])
    charter = load_charter(tmp_path)
    eng = Engine(tmp_path, charter.sources).start()
    try:
        tb = ToolBox(eng, charter.sources, recorder=FlightRecorder(tmp_path))
        await handle_message(
            _req(1, "initialize", {
                "protocolVersion": "2025-11-25",
                "clientInfo": {"name": "cursor", "version": "1.4"},
            }),
            tb,
        )
        await handle_message(_call(2, "query", sql="SELECT count(*) FROM store.orders"), tb)
    finally:
        eng.close()
    entries = read_entries(tmp_path)
    assert entries[0]["type"] == "session"
    assert entries[0]["surface"] == "mcp"
    assert entries[0]["client"] == {"name": "cursor", "version": "1.4"}
    assert entries[1]["type"] == "access" and entries[1]["tool"] == "query"
