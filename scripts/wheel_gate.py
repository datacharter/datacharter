#!/usr/bin/env python3
"""Release gate: run the smoke battery against the *installed* wheel.

Run inside an environment where the built wheel is installed (never the
editable checkout — the artifact is what ships). Boots a real server on a
demo workspace, runs datacharter.smoke, then exercises the MCP stdio server.
Exits non-zero on any failure; release publishing depends on this.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    from datacharter.smoke import format_results, run_battery  # from the wheel

    ws = Path(tempfile.mkdtemp(prefix="dc-gate-"))
    subprocess.run(
        [sys.executable, "-m", "datacharter.cli", "init", str(ws), "--demo"],
        check=True,
        capture_output=True,
    )

    port = free_port()
    server = subprocess.Popen(
        [sys.executable, "-m", "datacharter.cli", "serve", str(ws), "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        import httpx

        base = f"http://127.0.0.1:{port}"
        for _ in range(60):
            try:
                if httpx.get(f"{base}/api/health", timeout=2).status_code == 200:
                    break
            except Exception:
                time.sleep(1)
        else:
            print("gate FAILED: server never became healthy", file=sys.stderr)
            return 1

        results = run_battery(base)
        print(format_results(results))
        ok = all(passed for _, passed, _ in results)
    finally:
        server.terminate()
        server.wait(timeout=15)

    # MCP stdio: the second entry point must speak the protocol end to end.
    frames = "\n".join(
        json.dumps(f)
        for f in [
            {
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26", "capabilities": {},
                    "clientInfo": {"name": "gate", "version": "0"},
                },
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ]
    )
    proc = subprocess.run(
        [sys.executable, "-m", "datacharter.cli", "mcp", str(ws)],
        input=frames + "\n",
        capture_output=True,
        text=True,
        timeout=120,
    )
    tools: list[str] = []
    for line in proc.stdout.splitlines():
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("id") == 2:
            tools = [t["name"] for t in msg["result"]["tools"]]
    mcp_ok = set(tools) == {
        "list_sources", "list_tables", "describe_table", "query",
        "list_metrics", "query_metric",
    }
    print(f"  {'✓' if mcp_ok else '✗'} mcp-stdio: tools={tools}")

    ok = ok and mcp_ok
    print("wheel gate:", "OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
