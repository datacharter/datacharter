"""The Claude Code seam, exercised end-to-end in normal CI with a fake `claude`.

The real binary needs subscription auth, so this seam shipped broken twice
(dead bridge, dead tools) under green tests. The fake validates the exact argv
and config contract we drive Claude with (exit 64 on violation), and its happy
path spawns the REAL `datacharter mcp --serve-url` bridge and does a REAL
JSON-RPC handshake and tools/call against a live server — every layer between
`ask` and the data actually runs.
"""

import json
import socket
import sys
import threading
import time
from pathlib import Path

import httpx
import keyring
import keyring.backend
import pytest
import uvicorn

from datacharter.agent import claude_code as cc
from datacharter.cli import main as cli_main
from datacharter.server import create_app

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "fake_claude.py"

# The shim is a /bin/sh script; CI is ubuntu, dev machines are macOS.
pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX shim")


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


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def serve_url(tmp_path_factory):
    prev = keyring.get_keyring()
    keyring.set_keyring(_MemKeyring())
    ws = tmp_path_factory.mktemp("cc-harness-ws")
    assert cli_main(["init", str(ws)]) == 0
    (ws / "people.csv").write_text(
        "who,contact\nada,ada@example.com\ngrace,grace@example.com\nedsger,e@example.com\n"
    )
    (ws / "charter.yaml").write_text(
        "version: 1\nsources:\n  people:\n    type: csv\n    path: people.csv\n"
    )
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(create_app(ws), host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{url}/api/health", timeout=1.0).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.2)
    else:
        raise TimeoutError("test server never came up")
    yield url
    server.should_exit = True
    thread.join(timeout=10)
    keyring.set_keyring(prev)


@pytest.fixture
def fake_claude(tmp_path, monkeypatch):
    """Install the fake as the `claude` binary; returns a scenario setter."""
    shim = tmp_path / "claude"
    shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FIXTURE}" "$@"\n')
    shim.chmod(0o755)
    monkeypatch.setattr(cc, "find_claude", lambda: str(shim))

    def set_scenario(name: str) -> None:
        monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", name)

    return set_scenario


async def test_happy_path_runs_real_bridge_and_masks_pii(serve_url, fake_claude):
    fake_claude("HAPPY")
    deny = await cc.assert_tool_surface(serve_url)
    assert set(cc._DENY) <= set(deny)

    events = []
    async for ev in cc.run_turn(
        "what emails do we have?", serve_url, deny=deny,
        context=cc.system_context(""),
    ):
        events.append(ev)
    kinds = [e["kind"] for e in events]
    assert "session" in kinds and "tool_call" in kinds and "result" in kinds
    assert "error" not in kinds
    # The bridge's real query result flowed back through the fake's answer —
    # and the governed surface masked the value-detected email column.
    text = "".join(e.get("text", "") for e in events if e["kind"] == "text")
    assert "ada@example.com" not in text
    # ••• may arrive JSON-escaped (•) inside the rendered tool result.
    assert "•••" in text or "\\u2022\\u2022\\u2022" in text


async def test_extra_tools_are_auto_denied_via_real_probe(serve_url, fake_claude):
    fake_claude("EXTRA_TOOLS")
    deny = await cc.assert_tool_surface(serve_url)
    assert "Bash" in deny  # converged by denying the stray tool, not by luck


@pytest.mark.parametrize("scenario", ["NO_BRIDGE", "NO_INIT", "DRIFT"])
async def test_dead_or_drifted_tool_surface_refuses(serve_url, fake_claude, scenario):
    fake_claude(scenario)
    with pytest.raises(cc.ClaudeGovernanceError, match="missing"):
        await cc.assert_tool_surface(serve_url)


async def test_probe_hang_refuses_with_timeout(serve_url, fake_claude, monkeypatch):
    fake_claude("HANG")
    monkeypatch.setattr(cc, "_PROBE_TIMEOUT_S", 2.0)
    with pytest.raises(cc.ClaudeGovernanceError, match="did not respond"):
        await cc.assert_tool_surface(serve_url)


async def test_turn_hang_yields_error_event(serve_url, fake_claude, monkeypatch):
    fake_claude("HANG")
    monkeypatch.setattr(cc, "_TURN_IDLE_TIMEOUT_S", 2.0)
    events = [ev async for ev in cc.run_turn("q", serve_url, deny=list(cc._DENY))]
    assert events and events[-1]["kind"] == "error"
    assert "no output" in events[-1]["detail"]


async def test_exit1_surfaces_stderr_not_silence(serve_url, fake_claude):
    fake_claude("EXIT1_STDERR")
    events = [ev async for ev in cc.run_turn("q", serve_url, deny=list(cc._DENY))]
    assert events and events[-1]["kind"] == "error"
    assert "code 1" in events[-1]["detail"]
    assert "auth failure" in events[-1]["detail"]


async def test_argv_contract_is_enforced_by_the_fake(serve_url, fake_claude, tmp_path):
    """Meta-test: the fake really does refuse a bad drive. If run_turn ever
    stops passing --strict-mcp-config (the exact class of silent regression
    this harness exists for), the fake exits 64 and HAPPY tests fail."""
    import asyncio

    fake_claude("HAPPY")
    settings = tmp_path / "s.json"
    settings.write_text(json.dumps({"permissions": {"allow": cc.GOVERNED_TOOLS}}))
    mcp = tmp_path / "m.json"
    mcp.write_text(json.dumps({"mcpServers": {}}))
    proc = await asyncio.create_subprocess_exec(
        cc.find_claude(), "-p", "q", "--output-format", "stream-json",
        # no --strict-mcp-config, no --settings, no --permission-mode
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    assert proc.returncode == 64
    assert b"contract violation" in err


async def test_mcp_proxy_accesses_get_a_session(serve_url, fake_claude):
    # B-10: an external MCP client via --serve-url must attribute its accesses
    # to a real audit session, not session=''.
    from datacharter.agent.remote_tools import RemoteToolBox
    from datacharter.mcp.server import handle_message

    box = RemoteToolBox(serve_url)
    await handle_message(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"clientInfo": {"name": "probe", "version": "1"}}},
        box,
    )
    await box.run("query", '{"sql": "SELECT contact FROM people LIMIT 1"}')
    import httpx
    entries = httpx.get(f"{serve_url}/api/audit", timeout=10).json()["entries"]
    sessions = [e for e in entries if e.get("type") == "session" and e.get("surface") == "mcp"]
    assert sessions, "no mcp session recorded for the proxied access"
