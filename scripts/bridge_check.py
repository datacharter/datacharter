"""Prove the FROZEN app can serve as the Claude Code MCP bridge.

The desktop build has no `datacharter` console script — it re-execs itself
with an `mcp` argv. That dispatch shipped broken once (every Claude tool call
silently returned nothing), so CI now runs the real handshake against the
real binary: initialize, initialized, tools/list, one governed tools/call.

    python scripts/bridge_check.py <binary> <workspace>

stdlib only: runs inside the build venv on both macOS and Windows runners.
"""

import json
import subprocess
import sys

GOVERNED = {"query", "list_tables", "list_sources", "describe_table"}


def main() -> int:
    binary, workspace = sys.argv[1], sys.argv[2]
    frames = "\n".join(
        json.dumps(f)
        for f in [
            {
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                           "clientInfo": {"name": "bridge-check", "version": "0"}},
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "query", "arguments": {"sql": "SELECT 1 AS one"}}},
        ]
    )
    proc = subprocess.run(
        [binary, "mcp", workspace],
        input=frames + "\n", capture_output=True, text=True, timeout=180,
    )
    replies: dict = {}
    for line in proc.stdout.splitlines():
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "id" in msg:
            replies[msg["id"]] = msg

    def fail(why: str) -> int:
        print(f"bridge check FAILED: {why}", file=sys.stderr)
        print(f"stderr tail: {proc.stderr[-800:]}", file=sys.stderr)
        return 1

    if 1 not in replies or "result" not in replies[1]:
        return fail("no initialize response")
    if 2 not in replies or "result" not in replies[2]:
        return fail("no tools/list response")
    tools = {t["name"] for t in replies[2]["result"].get("tools", [])}
    if tools != GOVERNED:
        return fail(f"tool surface drifted: {sorted(tools)}")
    if 3 not in replies or "result" not in replies[3]:
        return fail("no tools/call response")
    text = "".join(c.get("text", "") for c in replies[3]["result"].get("content", []))
    if '"rows": [[1]]' not in text and "[[1]]" not in text.replace(" ", ""):
        return fail(f"query returned unexpected payload: {text[:200]}")
    print(f"bridge check OK: 4 governed tools, query round-trip verified ({binary})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
