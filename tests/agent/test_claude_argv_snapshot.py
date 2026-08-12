"""Snapshot of the exact argv we drive Claude Code with.

Any change to this surface is a governance-relevant event (a dropped
--strict-mcp-config silently reopens the user's own MCP servers) — this test
makes such a change show up as an explicit, reviewable diff.
"""

import asyncio
import json
from pathlib import Path

from datacharter.agent import claude_code as cc


class _FakeStdout:
    async def readline(self):
        return b""


class _FakeProc:
    stdout = _FakeStdout()
    stderr = None
    returncode = 0

    async def wait(self):
        return 0


async def _capture_argv(**kwargs) -> list[str]:
    captured: list[list[str]] = []
    real_exec = asyncio.create_subprocess_exec

    async def fake_exec(*args, **_kw):
        captured.append(list(args))
        return _FakeProc()

    asyncio.create_subprocess_exec = fake_exec
    try:
        async for _ in cc.run_turn("the question", "http://127.0.0.1:9", **kwargs):
            pass
    finally:
        asyncio.create_subprocess_exec = real_exec
    return captured[0]


def _shape(argv: list[str]) -> list[str]:
    """argv with volatile values (binary path, tmpdir configs) normalized."""
    out = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if i == 0:
            out.append("<claude>")
        elif a in ("--mcp-config", "--settings"):
            out += [a, f"<{a.lstrip('-')}>"]
            i += 1
        else:
            out.append(a)
        i += 1
    return out


def test_turn_argv_snapshot(monkeypatch, tmp_path):
    monkeypatch.setattr(cc, "find_claude", lambda: "/bin/claude")
    argv = asyncio.run(_capture_argv(context="CTX", session_id="sid-1"))
    assert _shape(argv) == [
        "<claude>",
        "-p", "the question",
        "--output-format", "stream-json",
        "--verbose",
        "--include-partial-messages",
        "--strict-mcp-config",
        "--mcp-config", "<mcp-config>",
        "--settings", "<settings>",
        "--permission-mode", "dontAsk",
        "--append-system-prompt", "CTX",
        "--resume", "sid-1",
    ]


def test_turn_argv_includes_model_when_pinned(monkeypatch):
    monkeypatch.setattr(cc, "find_claude", lambda: "/bin/claude")
    argv = asyncio.run(_capture_argv(model="sonnet"))
    assert argv[argv.index("--model") + 1] == "sonnet"


class _GradeProc:
    """A one-shot proc for `grade`, which uses communicate() not a readline loop."""

    stderr = None
    returncode = 0

    def __init__(self, stdout: bytes) -> None:
        self._stdout = stdout

    async def communicate(self):
        return self._stdout, b""

    def kill(self):
        self.returncode = -9

    async def wait(self):
        return self.returncode


def test_grade_pins_model_and_locks_the_sandbox(monkeypatch):
    """The judge is a distinct model with NO data tools and no MCP servers."""
    monkeypatch.setattr(cc, "find_claude", lambda: "/bin/claude")
    captured: dict = {}
    result_line = json.dumps(
        {"type": "result", "session_id": "j", "result": "PASS", "is_error": False}
    ).encode()

    async def fake_exec(*args, **_kw):
        argv = list(args)
        settings = json.loads(Path(argv[argv.index("--settings") + 1]).read_text())
        mcp = json.loads(Path(argv[argv.index("--mcp-config") + 1]).read_text())
        captured.update(argv=argv, settings=settings, mcp=mcp)
        return _GradeProc(result_line)

    real_exec = asyncio.create_subprocess_exec
    asyncio.create_subprocess_exec = fake_exec
    try:
        text = asyncio.run(cc.grade("grade this", model="opus", system="be a judge"))
    finally:
        asyncio.create_subprocess_exec = real_exec

    assert text == "PASS"
    argv = captured["argv"]
    assert argv[argv.index("--model") + 1] == "opus"
    assert "--strict-mcp-config" in argv  # judge can't reach the user's MCP servers
    assert captured["mcp"]["mcpServers"] == {}  # ...and has no data plane at all
    assert captured["settings"]["permissions"]["allow"] == []  # no tools granted
    assert "Bash" in captured["settings"]["permissions"]["deny"]  # built-ins denied


def test_turn_configs_lock_the_sandbox(monkeypatch):
    monkeypatch.setattr(cc, "find_claude", lambda: "/bin/claude")
    captured: dict = {}
    real_exec = asyncio.create_subprocess_exec

    async def fake_exec(*args, **_kw):
        argv = list(args)
        settings = json.loads(Path(argv[argv.index("--settings") + 1]).read_text())
        mcp = json.loads(Path(argv[argv.index("--mcp-config") + 1]).read_text())
        captured.update(settings=settings, mcp=mcp)
        return _FakeProc()

    async def run():
        asyncio.create_subprocess_exec = fake_exec
        try:
            async for _ in cc.run_turn("q", "http://127.0.0.1:9", deny=["Bash", "PluginX"]):
                pass
        finally:
            asyncio.create_subprocess_exec = real_exec

    asyncio.run(run())
    assert sorted(captured["settings"]["permissions"]["allow"]) == sorted(cc.GOVERNED_TOOLS)
    assert "PluginX" in captured["settings"]["permissions"]["deny"]
    bridge = captured["mcp"]["mcpServers"]["datacharter"]
    assert bridge["args"][0] == "mcp" and "--serve-url" in bridge["args"]
