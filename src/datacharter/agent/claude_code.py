"""Drive the local Claude Code (headless, subscription) as datacharter's agent backend.

Governance: every invocation is locked down (strict MCP config + a deny-list settings file +
`--permission-mode dontAsk`) and gated by a fail-closed tool-surface assertion. Claude reaches
data only through the governed `datacharter mcp --serve-url` proxy. Never uses `--bare` — that
disables subscription auth. Design: docs/superpowers/specs/2026-07-24-claude-code-agent-backend-design.md
"""  # noqa: E501

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
from collections.abc import AsyncIterator, Iterable, Iterator
from pathlib import Path

GOVERNED_TOOLS = [
    "mcp__datacharter__query",
    "mcp__datacharter__list_tables",
    "mcp__datacharter__list_sources",
    "mcp__datacharter__describe_table",
]

# Best-effort removal of built-ins. The connect-time assertion is the real guarantee;
# extend this from a clean-env `init.tools` list if the assertion reports a stray built-in.
_DENY = [
    "Bash", "Read", "Write", "Edit", "Glob", "Grep", "WebFetch", "WebSearch", "Agent",
    "Workflow", "Skill", "ToolSearch", "TaskCreate", "TaskGet", "TaskList", "TaskUpdate",
    "TaskStop", "TaskOutput", "ScheduleWakeup", "CronCreate", "CronDelete", "CronList",
    "SendMessage", "NotebookEdit", "Monitor", "WaitForMcpServers", "Artifact",
    "AskUserQuestion", "EnterPlanMode", "ExitPlanMode", "ReportFindings",
    "DesignSync", "EnterWorktree", "ExitWorktree", "PushNotification", "RemoteTrigger",
]


class ClaudeGovernanceError(RuntimeError):
    """Raised when Claude Code exposes tools beyond the governed set — connection refused."""


def claude_available() -> bool:
    return shutil.which("claude") is not None


def _dc_bin() -> str:
    # Must be the SAME datacharter that's serving (it needs `mcp --serve-url`); prefer the
    # console script next to the running interpreter over whatever is first on PATH.
    sibling = Path(sys.executable).parent / "datacharter"
    if sibling.exists():
        return str(sibling)
    return shutil.which("datacharter") or "datacharter"


def tool_surface_ok(tools: list[str]) -> bool:
    return set(tools).issubset(set(GOVERNED_TOOLS))


def build_configs(
    serve_url: str, dc_bin: str, tmpdir: Path, deny: list[str] | None = None
) -> tuple[Path, Path]:
    settings = tmpdir / "settings.json"
    mcp = tmpdir / "mcp.json"
    settings.write_text(
        json.dumps(
            {
                "defaultMode": "dontAsk",
                "permissions": {"allow": GOVERNED_TOOLS, "deny": deny or _DENY},
            }
        )
    )
    mcp.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "datacharter": {"command": dc_bin, "args": ["mcp", "--serve-url", serve_url]}
                }
            }
        )
    )
    return settings, mcp


def _base_flags(settings: Path, mcp: Path) -> list[str]:
    return [
        "--strict-mcp-config", "--mcp-config", str(mcp),
        "--settings", str(settings), "--permission-mode", "dontAsk",
    ]


def _env() -> dict:
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)  # force subscription auth
    return env


def parse_stream(lines: Iterable[str]) -> Iterator[dict]:
    """Map claude `stream-json` NDJSON lines to `{kind, ...}` events.

    kinds: `session` (init: session_id + tools), `tool_call` (governed tool + SQL),
    `text` (assistant delta), `result` (final text + session_id + is_error)."""
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            m = json.loads(raw)
        except json.JSONDecodeError:
            continue
        mtype = m.get("type")
        if mtype == "system" and m.get("subtype") == "init":
            yield {
                "kind": "session",
                "session_id": m.get("session_id"),
                "tools": m.get("tools", []),
            }
        elif mtype == "stream_event":
            ev = m.get("event", {}) or {}
            name = str(ev.get("name", ""))
            if ev.get("type") == "tool_use" and name.startswith("mcp__datacharter__"):
                label = ev["name"].removeprefix("mcp__datacharter__")
                sql = (ev.get("input") or {}).get("sql")
                yield {"kind": "tool_call", "tool": f"{label}: {sql}" if sql else label}
            delta = ev.get("delta") or {}
            if delta.get("type") == "text_delta" and delta.get("text"):
                yield {"kind": "text", "text": delta["text"]}
        elif mtype == "result":
            yield {
                "kind": "result",
                "session_id": m.get("session_id"),
                "text": m.get("result", ""),
                "is_error": m.get("is_error", False),
            }


async def probe_tools(
    serve_url: str, dc_bin: str | None = None, deny: list[str] | None = None
) -> list[str]:
    """Spawn a locked-down claude and return the tool names it actually exposes (init.tools)."""
    dc_bin = dc_bin or _dc_bin()
    with tempfile.TemporaryDirectory(prefix="dc-claude-") as td:
        settings, mcp = build_configs(serve_url, dc_bin, Path(td), deny)
        proc = await asyncio.create_subprocess_exec(
            "claude", "-p", "ok", "--output-format", "stream-json", "--verbose",
            *_base_flags(settings, mcp),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, env=_env(),
        )
        out, _ = await proc.communicate()
        for ev in parse_stream(out.decode().splitlines()):
            if ev["kind"] == "session":
                return ev.get("tools", [])
    return []


async def assert_tool_surface(serve_url: str, dc_bin: str | None = None) -> list[str]:
    """Fail-closed: probe Claude's tool surface, auto-deny any non-governed tools it finds,
    and re-probe until only the governed tools remain — returning the effective deny-list.
    Raises `ClaudeGovernanceError` if a non-governed tool cannot be disabled."""
    dc_bin = dc_bin or _dc_bin()
    deny = list(_DENY)
    extras: list[str] = []
    for _ in range(4):
        tools = await probe_tools(serve_url, dc_bin, deny)
        extras = sorted(set(tools) - set(GOVERNED_TOOLS))
        if not extras:
            return deny
        deny += [t for t in extras if t not in deny]  # deny only removes; loop converges
    raise ClaudeGovernanceError(
        "Refusing to connect: Claude Code exposes non-governed tools that could not be "
        "disabled: " + ", ".join(extras)
    )


async def run_turn(
    question: str,
    serve_url: str,
    session_id: str | None = None,
    dc_bin: str | None = None,
    deny: list[str] | None = None,
) -> AsyncIterator[dict]:
    """Run one chat turn; yield parsed stream events. Resumes `session_id` for context.
    `deny` is the effective deny-list from the connect-time assertion."""
    dc_bin = dc_bin or _dc_bin()
    with tempfile.TemporaryDirectory(prefix="dc-claude-") as td:
        settings, mcp = build_configs(serve_url, dc_bin, Path(td), deny)
        args = [
            "claude", "-p", question, "--output-format", "stream-json",
            "--verbose", "--include-partial-messages",
            *_base_flags(settings, mcp),
        ]
        if session_id:
            args += ["--resume", session_id]
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, env=_env()
        )
        assert proc.stdout is not None
        async for line in proc.stdout:
            for ev in parse_stream([line.decode()]):
                yield ev
        await proc.wait()
