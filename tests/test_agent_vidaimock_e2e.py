"""End-to-end: the agent loop round-trips through a live VidaiMock.

Boots VidaiMock (an OpenAI-wire mock LLM server) and `datacharter serve`, then
drives `/api/agent/ask` and asserts the full tool_call -> execute -> synthesize
SSE loop over the demo workspace. Proves wire compatibility and loop termination
against a real socket — NOT answer correctness (VidaiMock returns templated
text, not reasoning).

Requires the VidaiMock binary (Apache-2.0, github.com/vidaiUK/VidaiMock): set
`VIDAIMOCK_BIN` to its path or put `vidaimock` on PATH. Marked `e2e`, so it is
excluded from the default `pytest -q` run and gated behind `-m e2e`.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from datacharter.cli import main as cli_main

pytestmark = pytest.mark.e2e


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_port(port: int, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as sock:
            sock.settimeout(0.5)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.3)
    raise TimeoutError(f"nothing listening on 127.0.0.1:{port}")


def _wait_health(base_url: str, timeout: float = 25.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{base_url}/api/health", timeout=1.0).status_code == 200:
                return True
        except httpx.HTTPError:
            time.sleep(0.4)
    return False


def _vidaimock_bin() -> str:
    binary = os.environ.get("VIDAIMOCK_BIN") or shutil.which("vidaimock")
    if not binary or not Path(binary).exists():
        pytest.skip("VidaiMock not available; set VIDAIMOCK_BIN or put `vidaimock` on PATH")
    return binary


@pytest.fixture
def vidaimock_url():
    port = _free_port()
    proc = subprocess.Popen(
        [_vidaimock_bin(), "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_port(port)
        yield f"http://127.0.0.1:{port}/v1"
    finally:
        proc.terminate()
        proc.wait(timeout=10)


@pytest.fixture
def serve_url(tmp_path, vidaimock_url):
    assert cli_main(["init", str(tmp_path), "--demo"]) == 0
    port = _free_port()
    log = tmp_path / "serve.log"
    dc = str(Path(sys.executable).with_name("datacharter"))
    env = {**os.environ, "OPENAI_BASE_URL": vidaimock_url, "OPENAI_API_KEY": "test"}
    with open(log, "wb") as fh:
        proc = subprocess.Popen(
            [dc, "serve", str(tmp_path), "--port", str(port)],
            env=env,
            stdout=fh,
            stderr=subprocess.STDOUT,
        )
        try:
            base = f"http://127.0.0.1:{port}"
            if not _wait_health(base):
                pytest.fail(f"serve did not come up:\n{log.read_text()[-2000:]}")
            yield base
        finally:
            proc.terminate()
            proc.wait(timeout=10)


def _drive_agent(base_url: str, question: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    with httpx.stream(
        "POST", f"{base_url}/api/agent/ask", json={"question": question}, timeout=30.0
    ) as resp:
        resp.raise_for_status()
        kind: str | None = None
        for line in resp.iter_lines():
            if line.startswith("event: "):
                kind = line[len("event: ") :]
            elif line.startswith("data: ") and kind:
                events.append((kind, json.loads(line[len("data: ") :])))
                if kind == "done":
                    break
    return events


def test_agent_available_through_vidaimock(serve_url):
    body = httpx.get(f"{serve_url}/api/agent/available", timeout=5.0).json()
    assert body["available"] is True
    assert body["base_url"].endswith("/v1")


def test_agent_loop_roundtrips_through_vidaimock(serve_url):
    events = _drive_agent(serve_url, "How many customers are there?")
    kinds = [k for k, _ in events]

    assert "tool_call" in kinds, kinds  # the model asked to call a tool
    assert "tool_result" in kinds, kinds  # the tool actually executed
    assert "text" in kinds, kinds  # synthesis streamed back
    assert kinds[-1] == "done"

    # the tool ran against the real demo workspace (the store contract), not a stub
    payloads = " ".join(json.dumps(d) for _, d in events)
    assert "store" in payloads
