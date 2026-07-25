import pytest

from datacharter.agent import claude_code as cc
from datacharter.agent.claude_code import (
    GOVERNED_TOOLS,
    build_configs,
    parse_stream,
    tool_surface_ok,
)


def test_parse_stream_maps_events():
    lines = [
        '{"type":"system","subtype":"init","tools":["mcp__datacharter__query"],"session_id":"s1"}',
        '{"type":"stream_event","event":{"type":"tool_use","name":"mcp__datacharter__query","input":{"sql":"SELECT 1"}}}',  # noqa: E501
        '{"type":"stream_event","event":{"delta":{"type":"text_delta","text":"Hello"}}}',
        "",
        "not json",
        '{"type":"result","result":"Hello","session_id":"s1","is_error":false}',
    ]
    evs = list(parse_stream(lines))
    kinds = [e["kind"] for e in evs]
    assert kinds == ["session", "tool_call", "text", "result"]
    assert evs[0]["tools"] == ["mcp__datacharter__query"] and evs[0]["session_id"] == "s1"
    assert "SELECT 1" in next(e for e in evs if e["kind"] == "tool_call")["tool"]
    assert evs[-1]["text"] == "Hello" and evs[-1]["is_error"] is False


def test_tool_surface_ok():
    assert tool_surface_ok(GOVERNED_TOOLS) is True
    assert tool_surface_ok(["mcp__datacharter__query"]) is True   # subset ok
    assert tool_surface_ok(GOVERNED_TOOLS + ["Bash"]) is False
    assert tool_surface_ok(["Bash"]) is False


async def test_assert_tool_surface_auto_denies_extras(monkeypatch):
    async def fake_probe(serve_url, dc_bin=None, deny=None):
        # a plugin tool that goes away once denied
        return GOVERNED_TOOLS if "PluginX" in (deny or []) else [*GOVERNED_TOOLS, "PluginX"]

    monkeypatch.setattr(cc, "probe_tools", fake_probe)
    deny = await cc.assert_tool_surface("http://x")
    assert "PluginX" in deny


async def test_assert_tool_surface_refuses_undeniable(monkeypatch):
    async def fake_probe(serve_url, dc_bin=None, deny=None):
        return [*GOVERNED_TOOLS, "Stubborn"]  # never removable

    monkeypatch.setattr(cc, "probe_tools", fake_probe)
    with pytest.raises(cc.ClaudeGovernanceError, match="Stubborn"):
        await cc.assert_tool_surface("http://x")


def test_build_configs_locks_down(tmp_path):
    import json

    settings, mcp = build_configs("http://127.0.0.1:9", "/bin/datacharter", tmp_path)
    s = json.loads(settings.read_text())
    assert s["defaultMode"] == "dontAsk"
    assert set(GOVERNED_TOOLS) <= set(s["permissions"]["allow"])
    assert "Bash" in s["permissions"]["deny"] and "Agent" in s["permissions"]["deny"]
    m = json.loads(mcp.read_text())
    assert m["mcpServers"]["datacharter"]["args"] == ["mcp", "--serve-url", "http://127.0.0.1:9"]
