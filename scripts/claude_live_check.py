"""The Claude Code round of the release gate, automated against the REAL claude.

CI runs a fake claude (no subscription auth there); this runs on the release
machine, where the real binary lives, and does what the human ritual did:
connect through the tool-surface assertion, ask a data question (expect real
tool calls + an answer from data, not file-hunting), ask about value-detected
PII (expect •••, never the raw value), then a follow-up on the same session
(memory). If Ollama is running, a local-model round exercises the
switch-backend path through the served API.

    python scripts/claude_live_check.py --bin .venv/bin/datacharter

Exit 0 = every round passed. Prints a per-round report; the release gate
embeds it in docs/releases/v<X>-verified.txt.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _make_workspace(dc_bin: str) -> Path:
    ws = Path(tempfile.mkdtemp(prefix="dc-live-check-")) / "ws"
    subprocess.run([dc_bin, "init", str(ws)], check=True, capture_output=True)
    (ws / "people.csv").write_text(
        "who,contact\nada,ada@example.com\ngrace,grace@example.com\nedsger,e@example.com\n"
    )
    (ws / "charter.yaml").write_text(
        "version: 1\nsources:\n  people:\n    type: csv\n    path: people.csv\n"
    )
    return ws


async def _collect(gen) -> list[dict]:
    return [ev async for ev in gen]


def _text_of(events: list[dict]) -> str:
    text = "".join(e.get("text", "") for e in events if e["kind"] == "text")
    result = next((e for e in events if e["kind"] == "result"), None)
    return text or (result.get("text", "") if result else "")


async def run_rounds(serve_url: str, dc_bin: str) -> list[tuple[str, bool, str]]:
    from datacharter.agent import claude_code as cc

    results: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        results.append((name, ok, detail))

    version = cc.claude_version() or "unknown"
    check("claude-binary", cc.claude_available(), version)
    if not cc.claude_available():
        return results

    try:
        deny = await cc.assert_tool_surface(serve_url, dc_bin=dc_bin)
        check("tool-surface", True, f"governed surface asserted ({len(deny)} denied)")
    except cc.ClaudeGovernanceError as exc:
        check("tool-surface", False, str(exc))
        return results

    context = cc.system_context("")

    # Round: a data question must be answered FROM data, through the tools.
    events = await _collect(cc.run_turn(
        "How many rows are in the people table? Answer with the number.",
        serve_url, dc_bin=dc_bin, deny=deny, context=context,
    ))
    calls = [e for e in events if e["kind"] == "tool_call"]
    errors = [e for e in events if e["kind"] == "error"]
    answer = _text_of(events)
    session_id = next(
        (e.get("session_id") for e in events if e["kind"] in ("session", "result")), None
    )
    check(
        "data-question",
        bool(calls) and not errors and "3" in answer,
        f"tools={[c['tool'] for c in calls]} answer={answer[:80]!r}"
        + (f" errors={errors}" if errors else ""),
    )

    # Round: value-detected PII must come back masked, never raw.
    events = await _collect(cc.run_turn(
        "Show me one value from the contact column of the people table.",
        serve_url, dc_bin=dc_bin, deny=deny, context=context,
    ))
    blob = json.dumps(events)
    check(
        "pii-masked",
        "ada@example.com" not in blob and "grace@example.com" not in blob,
        "raw emails absent from every event"
        if "ada@example.com" not in blob
        else "RAW EMAIL LEAKED to agent output",
    )

    # Round: a follow-up on the same session proves conversational memory.
    if session_id:
        events = await _collect(cc.run_turn(
            "What was that row count again? Just the number.",
            serve_url, session_id=session_id, dc_bin=dc_bin, deny=deny, context=context,
        ))
        followup = _text_of(events)
        errors = [e for e in events if e["kind"] == "error"]
        check("follow-up-memory", not errors and "3" in followup, f"answer={followup[:80]!r}")
    else:
        check("follow-up-memory", False, "no session id captured from first turn")

    return results


def run_local_llm_round(serve_url: str) -> tuple[str, bool, str]:
    """Backend-switch round: if a local runtime is up, connect it and ask."""
    with httpx.Client(base_url=serve_url, timeout=180) as client:
        runtimes = client.get("/api/llm/local").json().get("runtimes", [])
        if not runtimes:
            return ("local-llm", True, "skipped — no local runtime running")
        rt = runtimes[0]
        model = rt["models"][0]
        client.post(
            "/api/agent/config", json={"base_url": rt["base_url"], "model": model}
        ).raise_for_status()
        answer = ""
        with client.stream(
            "POST", "/api/agent/ask",
            json={"question": "How many rows are in the people table?"},
        ) as resp:
            for line in resp.iter_lines():
                if line.startswith("data:"):
                    try:
                        payload = json.loads(line[5:])
                    except json.JSONDecodeError:
                        continue
                    answer += payload.get("text") or ""
        ok = bool(answer.strip())
        return ("local-llm", ok, f"{rt['provider']}/{model}: {answer[:80]!r}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bin", default=".venv/bin/datacharter")
    args = parser.parse_args()
    dc_bin = str(Path(args.bin).resolve())

    ws = _make_workspace(dc_bin)
    port = _free_port()
    serve = subprocess.Popen(
        [dc_bin, "serve", str(ws), "--port", str(port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    serve_url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                if httpx.get(f"{serve_url}/api/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.5)
        else:
            print("server never came up", file=sys.stderr)
            return 1

        results = asyncio.run(run_rounds(serve_url, dc_bin))
        results.append(run_local_llm_round(serve_url))
    finally:
        serve.terminate()
        serve.wait(timeout=10)

    failed = [r for r in results if not r[1]]
    for name, ok, detail in results:
        print(f"  {'✓' if ok else '✗'} {name}: {detail}")
    print(f"claude live check: {len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
