"""mcp --guard: heuristic firewall in front of an upstream MCP server."""

import json

from datacharter.agent.tools import MASKED
from datacharter.audit.canary import CanaryGuard
from datacharter.audit.recorder import FLIGHT_DIR, FlightRecorder
from datacharter.cli import main as cli_main
from datacharter.mcp.guard import GuardProxy


class ScriptedUpstream:
    def __init__(self, by_method: dict):
        self.by_method = by_method
        self.calls = []

    async def rpc(self, message: dict) -> dict | None:
        self.calls.append(message)
        if "id" not in message:
            return None
        method = message.get("method")
        reply = self.by_method[method]
        if callable(reply):
            reply = reply(message)
        return {"jsonrpc": "2.0", "id": message["id"], **reply}


def _call(name, **arguments):
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }


def _text_result(text: str) -> dict:
    return {"result": {"content": [{"type": "text", "text": text}], "isError": False}}


async def test_tools_list_comes_from_upstream():
    tools = [{"name": "search", "inputSchema": {"type": "object"}}]
    up = ScriptedUpstream({"tools/list": {"result": {"tools": tools}}})
    resp = await GuardProxy(up).handle({"jsonrpc": "2.0", "id": 7, "method": "tools/list"})
    names = {t["name"] for t in resp["result"]["tools"]}
    assert names == {"search"}
    assert "query" not in names


async def test_email_in_tool_result_is_redacted():
    up = ScriptedUpstream({
        "tools/call": _text_result("contact alice@example.com please"),
    })
    resp = await GuardProxy(up).handle(_call("inbox.read"))
    text = resp["result"]["content"][0]["text"]
    assert "alice@example.com" not in text
    assert MASKED in text


async def test_ssn_in_tool_result_is_redacted():
    up = ScriptedUpstream({"tools/call": _text_result("ssn 123-45-6789")})
    resp = await GuardProxy(up).handle(_call("lookup"))
    text = resp["result"]["content"][0]["text"]
    assert "123-45-6789" not in text
    assert MASKED in text


async def test_records_redacted_access_not_raw_email(tmp_path):
    rec = FlightRecorder(tmp_path, sink=None)
    rec.start_session("mcp-guard")
    up = ScriptedUpstream({
        "tools/call": _text_result("mail alice@example.com"),
    })
    await GuardProxy(up, recorder=rec).handle(_call("inbox.read"))
    blob = ""
    for seg in (tmp_path / FLIGHT_DIR).glob("*.jsonl"):
        blob += seg.read_text()
    assert "alice@example.com" not in blob
    assert '"type": "access"' in blob or '"type":"access"' in blob


async def test_canary_block_withholds_result(tmp_path):
    rec = FlightRecorder(tmp_path, sink=None)
    rec.start_session("mcp-guard")
    guard = CanaryGuard(tokens=["canary-deadbeef"], mode="block")
    up = ScriptedUpstream({
        "tools/call": _text_result("token canary-deadbeef leaked"),
    })
    resp = await GuardProxy(up, recorder=rec, canary=guard).handle(_call("dump"))
    text = resp["result"]["content"][0]["text"]
    assert resp["result"]["isError"] is True
    assert "canary" in text.lower()
    assert "canary-deadbeef" not in text
    entries = []
    for seg in (tmp_path / FLIGHT_DIR).glob("*.jsonl"):
        for line in seg.read_text().splitlines():
            if line.strip():
                entries.append(json.loads(line))
    assert any(e.get("type") == "alarm" for e in entries)


async def test_huge_result_is_truncated():
    up = ScriptedUpstream({"tools/call": _text_result("x" * 5000)})
    resp = await GuardProxy(up, max_bytes=100).handle(_call("dump"))
    text = resp["result"]["content"][0]["text"]
    assert len(text.encode()) <= 200
    assert "truncated" in text.lower()


def test_cli_guard_cannot_combine_with_http_or_serve_url(capsys):
    assert cli_main(["mcp", ".", "--guard", "true", "--http"]) == 1
    assert "--http" in capsys.readouterr().err
    assert cli_main(["mcp", ".", "--guard", "true", "--serve-url", "http://127.0.0.1"]) == 1
    assert "--serve-url" in capsys.readouterr().err


async def test_stdio_upstream_roundtrip(tmp_path):
    import sys

    from datacharter.mcp.guard import StdioUpstream

    script = tmp_path / "up.py"
    script.write_text(
        "import json,sys\n"
        "msg=json.loads(sys.stdin.readline())\n"
        "print(json.dumps({'jsonrpc':'2.0','id':msg['id'],'result':{}}), flush=True)\n"
    )
    up = StdioUpstream([sys.executable, str(script)])
    try:
        resp = await up.rpc({"jsonrpc": "2.0", "id": 3, "method": "ping"})
        assert resp["id"] == 3 and resp["result"] == {}
    finally:
        up.close()


def test_cli_guard_needs_a_command(tmp_path, capsys):
    cli_main(["init", str(tmp_path)])
    capsys.readouterr()
    assert cli_main(["mcp", str(tmp_path), "--guard", "   "]) == 1
    assert "upstream" in capsys.readouterr().err.lower()
