"""A stand-in `claude` binary for CI: same argv contract, same stream-json output.

The real Claude Code cannot run in CI (subscription auth), so every seam around
it — argv construction, config files, the MCP bridge subprocess, stream parsing,
timeout/exit handling — previously went untested and shipped broken. This fake:

1. VALIDATES the argv/config contract (exit 64 on any violation, so a drive-side
   regression fails loudly instead of silently passing), and
2. In the HAPPY path, actually SPAWNS the real MCP bridge from mcp.json and does
   a real JSON-RPC handshake + tools/call — the seam that shipped dead twice.

Scenarios via FAKE_CLAUDE_SCENARIO: HAPPY (default), EXTRA_TOOLS, NO_BRIDGE,
HANG, EXIT1_STDERR, NO_INIT, DRIFT.
"""

import json
import os
import subprocess
import sys
import time

GOVERNED = [
    "mcp__datacharter__query",
    "mcp__datacharter__list_tables",
    "mcp__datacharter__list_sources",
    "mcp__datacharter__describe_table",
    "mcp__datacharter__list_metrics",
    "mcp__datacharter__query_metric",
]

CONTRACT_VIOLATION = 64


def die(msg: str) -> None:
    print(f"fake-claude contract violation: {msg}", file=sys.stderr)
    sys.exit(CONTRACT_VIOLATION)


def parse_argv(argv: list[str]) -> dict:
    opts: dict = {"flags": set()}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-p", "--mcp-config", "--settings", "--permission-mode",
                 "--output-format", "--append-system-prompt", "--resume"):
            if i + 1 >= len(argv):
                die(f"{a} missing its value")
            opts[a] = argv[i + 1]
            i += 2
        else:
            opts["flags"].add(a)
            i += 1
    return opts


def validate(opts: dict) -> tuple[dict, dict]:
    for required in ("-p", "--mcp-config", "--settings", "--permission-mode",
                     "--output-format"):
        if required not in opts:
            die(f"missing {required}")
    if opts["--output-format"] != "stream-json":
        die("--output-format must be stream-json")
    if opts["--permission-mode"] != "dontAsk":
        die("--permission-mode must be dontAsk")
    if "--strict-mcp-config" not in opts["flags"]:
        die("--strict-mcp-config missing: a non-strict config loads user MCP servers")
    try:
        from pathlib import Path

        settings = json.loads(Path(opts["--settings"]).read_text())
        mcp = json.loads(Path(opts["--mcp-config"]).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        die(f"unreadable config: {exc}")
    if sorted(settings.get("permissions", {}).get("allow", [])) != sorted(GOVERNED):
        die("settings allow-list is not exactly the governed tools")
    server = mcp.get("mcpServers", {}).get("datacharter")
    if not server or not server.get("command") or "mcp" not in server.get("args", []):
        die("mcp.json must define the datacharter bridge command")
    return settings, mcp


def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


class Bridge:
    """The real `datacharter mcp` subprocess, driven over real JSON-RPC stdio."""

    def __init__(self, server: dict) -> None:
        self.proc = subprocess.Popen(
            [server["command"], *server.get("args", [])],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True,
        )
        self._id = 0

    def call(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        frame = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            frame["params"] = params
        assert self.proc.stdin is not None and self.proc.stdout is not None
        self.proc.stdin.write(json.dumps(frame) + "\n")
        self.proc.stdin.flush()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            line = self.proc.stdout.readline()
            if not line:
                break
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("id") == self._id:
                if "error" in msg:
                    die(f"bridge error on {method}: {msg['error']}")
                return msg.get("result", {})
        stderr = self.proc.stderr.read() if self.proc.stderr else ""
        die(f"bridge gave no response to {method}; stderr: {stderr[-500:]}")
        raise AssertionError  # unreachable

    def notify(self, method: str) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method}) + "\n")
        self.proc.stdin.flush()

    def handshake(self) -> list[str]:
        self.call("initialize", {
            "protocolVersion": "2025-03-26", "capabilities": {},
            "clientInfo": {"name": "fake-claude", "version": "0"},
        })
        self.notify("notifications/initialized")
        tools = self.call("tools/list").get("tools", [])
        return [f"mcp__datacharter__{t['name']}" for t in tools]

    def close(self) -> None:
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


def main() -> int:
    opts = parse_argv(sys.argv[1:])
    settings, mcp = validate(opts)
    scenario = os.environ.get("FAKE_CLAUDE_SCENARIO", "HAPPY")
    deny = set(settings.get("permissions", {}).get("deny", []))
    sid = "fake-session-1"

    if scenario == "HANG":
        time.sleep(3600)
        return 0
    if scenario == "EXIT1_STDERR":
        print("fake-claude: simulated auth failure", file=sys.stderr)
        return 1
    if scenario == "NO_INIT":
        emit({"type": "result", "result": "no init ever sent", "session_id": sid,
              "is_error": False})
        return 0
    if scenario == "NO_BRIDGE":
        emit({"type": "system", "subtype": "init", "tools": [], "session_id": sid})
        emit({"type": "result", "result": "", "session_id": sid, "is_error": False})
        return 0
    if scenario == "DRIFT":
        drifted = [t.replace("query", "run_sql") for t in GOVERNED]
        emit({"type": "system", "subtype": "init", "tools": drifted, "session_id": sid})
        emit({"type": "result", "result": "", "session_id": sid, "is_error": False})
        return 0

    # HAPPY / EXTRA_TOOLS: a real bridge, a real handshake, a real tool call.
    bridge = Bridge(mcp["mcpServers"]["datacharter"])
    try:
        tools = bridge.handshake()
        if scenario == "EXTRA_TOOLS" and "Bash" not in deny:
            tools = [*tools, "Bash"]
        emit({"type": "system", "subtype": "init", "tools": tools, "session_id": sid})

        sql = os.environ.get(
            "FAKE_CLAUDE_SQL", "SELECT contact FROM people LIMIT 1"
        )
        emit({"type": "stream_event", "event": {
            "type": "tool_use", "name": "mcp__datacharter__query", "input": {"sql": sql},
        }})
        result = bridge.call("tools/call", {"name": "query", "arguments": {"sql": sql}})
        text = "".join(c.get("text", "") for c in result.get("content", []))
        emit({"type": "stream_event", "event": {
            "delta": {"type": "text_delta", "text": f"The query returned: {text}"},
        }})
        emit({"type": "result", "result": f"The query returned: {text}",
              "session_id": sid, "is_error": False})
    finally:
        bridge.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
