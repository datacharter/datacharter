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
    assert next(e for e in evs if e["kind"] == "tool_call")["sql"] == "SELECT 1"
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


def test_deny_list_round_trips(tmp_path):
    assert cc.load_deny(tmp_path) is None
    cc.save_deny(tmp_path, ["Bash", "CustomPluginTool"])
    assert cc.load_deny(tmp_path) == ["Bash", "CustomPluginTool"]


async def test_assert_tool_surface_warm_starts_from_persisted_deny(monkeypatch):
    seen = {}

    async def fake_probe(url, dc_bin=None, deny=None):
        seen["deny"] = deny
        return GOVERNED_TOOLS  # a clean surface

    monkeypatch.setattr(cc, "probe_tools", fake_probe)
    deny = await cc.assert_tool_surface("http://x", initial_deny=["CustomPluginTool"])
    assert "CustomPluginTool" in seen["deny"]  # persisted list warm-started the probe
    assert "CustomPluginTool" in deny


async def test_run_turn_aborts_on_stall(monkeypatch):
    import asyncio

    class _HangStdout:
        async def readline(self):
            await asyncio.sleep(3600)

    class _Stderr:
        async def read(self):
            return b"claude boom"

    class _FakeProc:
        def __init__(self):
            self.returncode = None
            self.stdout = _HangStdout()
            self.stderr = _Stderr()

        def kill(self):
            self.returncode = -9

        async def wait(self):
            return self.returncode

    async def fake_exec(*a, **k):
        return _FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(cc, "_TURN_IDLE_TIMEOUT_S", 0.2)
    events = [ev async for ev in cc.run_turn("q", "http://x")]
    errs = [e for e in events if e["kind"] == "error"]
    assert errs and "no output" in errs[0]["detail"]
    assert "boom" in errs[0]["detail"]


def test_claude_found_when_path_is_minimal(tmp_path, monkeypatch):
    """A GUI-launched app has a minimal PATH; detection must still find the CLI."""
    import os as _os

    from datacharter.agent import claude_code as cc

    fake_home = tmp_path / "home"
    (fake_home / ".local" / "bin").mkdir(parents=True)
    binary = fake_home / ".local" / "bin" / "claude"
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)

    monkeypatch.setattr(cc.shutil, "which", lambda _n: None)  # not on PATH at all
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setattr(_os.path, "expanduser", lambda p: p.replace("~", str(fake_home)))

    assert cc.find_claude() == str(binary)
    assert cc.claude_available() is True


def test_claude_absent_reports_unavailable(monkeypatch):
    from datacharter.agent import claude_code as cc

    monkeypatch.setattr(cc.shutil, "which", lambda _n: None)
    monkeypatch.setattr(cc, "_EXTRA_BIN_DIRS", ())
    assert cc.find_claude() is None and cc.claude_available() is False


def test_system_context_frames_the_data_agent():
    # Claude Code's default persona hunts the filesystem for data questions —
    # every turn must carry the data-agent framing (user-reported).
    from datacharter.agent.claude_code import system_context

    ctx = system_context(None)
    for must in ("MCP tools", "list_tables", "query", "Do not search for files"):
        assert must in ctx
    with_guides = system_context("- revenue is net of refunds")
    assert with_guides.startswith(ctx)
    assert "revenue is net of refunds" in with_guides
