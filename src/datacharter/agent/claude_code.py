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


_PROBE_TIMEOUT_S = 60.0  # a locked-down probe should return init.tools quickly
_TURN_IDLE_TIMEOUT_S = 120.0  # abort a turn that produces no output for this long
_STDERR_TAIL = 2000  # chars of stderr to surface when a subprocess fails


class ClaudeGovernanceError(RuntimeError):
    """Raised when Claude Code exposes tools beyond the governed set — connection refused."""


#: Where CLI tools actually live. A GUI-launched app (Finder/Dock, or the frozen
#: desktop build) inherits a minimal PATH that omits all of these, so `which`
#: alone would report "not installed" on a machine that clearly has it.
_EXTRA_BIN_DIRS = (
    "~/.local/bin", "~/.claude/local", "~/bin",
    "/opt/homebrew/bin", "/usr/local/bin",
    "~/.npm-global/bin", "~/.bun/bin", "~/.volta/bin",
)


def find_claude() -> str | None:
    """Absolute path to the `claude` binary, searching beyond a GUI app's PATH."""
    found = shutil.which("claude")
    if found:
        return found
    name = "claude.exe" if os.name == "nt" else "claude"
    for d in _EXTRA_BIN_DIRS:
        candidate = Path(d).expanduser() / name
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def claude_available() -> bool:
    return find_claude() is not None


def _deny_path(workspace: Path) -> Path:
    return Path(workspace) / ".datacharter" / "cc_deny.json"


def save_deny(workspace: Path, deny: list[str]) -> None:
    """Persist the asserted deny-list so a restart needn't re-probe Claude Code."""
    path = _deny_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(deny))


def load_deny(workspace: Path) -> list[str] | None:
    """The persisted deny-list, or None if absent/unreadable."""
    path = _deny_path(workspace)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, list) else None


async def _stderr_tail(proc) -> str:
    if proc.stderr is None:
        return ""
    try:
        data = await asyncio.wait_for(proc.stderr.read(), timeout=2.0)
    except (TimeoutError, Exception):  # noqa: BLE001 — best-effort diagnostics only
        return ""
    text = data.decode(errors="replace").strip()
    return f" (claude stderr: {text[-_STDERR_TAIL:]})" if text else ""


def _dc_bin() -> str:
    # Must be the SAME datacharter that's serving (it needs `mcp --serve-url`).
    # Frozen desktop app: there is no console script — the app binary re-execs
    # itself (the desktop entry dispatches an `mcp` argv to the CLI). Otherwise
    # prefer the script next to the running interpreter over whatever's on PATH
    # (a PATH hit could be a different, version-mismatched install).
    if getattr(sys, "frozen", False):
        return sys.executable
    sibling = Path(sys.executable).parent / "datacharter"
    if sibling.exists():
        return str(sibling)
    return shutil.which("datacharter") or "datacharter"


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
                yield {"kind": "tool_call", "tool": label, "sql": sql or ""}
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
            find_claude() or "claude", "-p", "ok", "--output-format", "stream-json", "--verbose",
            *_base_flags(settings, mcp),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=_env(),
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=_PROBE_TIMEOUT_S)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise ClaudeGovernanceError(
                f"Claude Code did not respond within {_PROBE_TIMEOUT_S:.0f}s during the "
                "tool-surface probe; refusing to connect."
            ) from None
        for ev in parse_stream(out.decode().splitlines()):
            if ev["kind"] == "session":
                return ev.get("tools", [])
    return []


async def assert_tool_surface(
    serve_url: str, dc_bin: str | None = None, initial_deny: list[str] | None = None
) -> list[str]:
    """Fail-closed: probe Claude's tool surface, auto-deny any non-governed tools it finds,
    and re-probe until only the governed tools remain — returning the effective deny-list.
    Raises `ClaudeGovernanceError` if a non-governed tool cannot be disabled.

    `initial_deny` (e.g. a persisted deny-list) warm-starts the loop so a reconnect
    converges in one probe; the assertion still runs, so a newly-appeared tool is caught."""
    dc_bin = dc_bin or _dc_bin()
    deny = list(_DENY) + [t for t in (initial_deny or []) if t not in _DENY]
    extras: list[str] = []
    for _ in range(4):
        tools = await probe_tools(serve_url, dc_bin, deny)
        # Fail closed in BOTH directions: extra tools are a governance breach,
        # but MISSING governed tools mean the MCP bridge is dead — connecting
        # anyway gives an agent that silently answers nothing.
        missing = sorted(set(GOVERNED_TOOLS) - set(tools))
        if missing:
            raise ClaudeGovernanceError(
                "Refusing to connect: the DataCharter data tools are not reachable "
                f"from Claude Code (missing: {', '.join(missing)}). The MCP bridge "
                f"({dc_bin}) likely failed to start — reconnect after checking that "
                "the app can launch its own `mcp` subprocess."
            )
        extras = sorted(set(tools) - set(GOVERNED_TOOLS))
        if not extras:
            return deny
        deny += [t for t in extras if t not in deny]  # deny only removes; loop converges
    raise ClaudeGovernanceError(
        "Refusing to connect: Claude Code exposes non-governed tools that could not be "
        "disabled: " + ", ".join(extras)
    )


#: Claude Code's own identity is "coding assistant in a repo" — without strong
#: framing it hunts the filesystem for data questions. This context redirects
#: it to the governed tools, which are the only path to the data anyway.
AGENT_FRAMING = """\
You are DataCharter's data agent. The user's question is about the DATA in \
their connected DataCharter workspace — it is never about files or code on \
this machine.

Answer exclusively through the DataCharter MCP tools: list_sources, \
list_tables, describe_table, and query (read-only SQL). Do not search for \
files, do not read paths, do not suggest opening anything on disk — the data \
is reachable only through those tools. If unsure of the schema, start with \
list_tables or describe_table, then run SQL with query and answer concisely \
from the results. PII columns come back masked as ••• — never guess at \
masked values."""


def system_context(guides: str | None) -> str:
    """The full --append-system-prompt: agent framing plus workspace guides."""
    if guides:
        return AGENT_FRAMING + "\n\n# Workspace guides\n" + guides
    return AGENT_FRAMING


async def run_turn(
    question: str,
    serve_url: str,
    session_id: str | None = None,
    dc_bin: str | None = None,
    deny: list[str] | None = None,
    context: str | None = None,
) -> AsyncIterator[dict]:
    """Run one chat turn; yield parsed stream events. Resumes `session_id` for context.
    `deny` is the effective deny-list from the connect-time assertion; `context` is
    workspace-guide text appended to the system prompt."""
    dc_bin = dc_bin or _dc_bin()
    with tempfile.TemporaryDirectory(prefix="dc-claude-") as td:
        settings, mcp = build_configs(serve_url, dc_bin, Path(td), deny)
        args = [
            find_claude() or "claude", "-p", question, "--output-format", "stream-json",
            "--verbose", "--include-partial-messages",
            *_base_flags(settings, mcp),
        ]
        if context:
            args += ["--append-system-prompt", context]
        if session_id:
            args += ["--resume", session_id]
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=_env()
        )
        assert proc.stdout is not None
        saw_result = False
        try:
            while True:
                try:
                    line = await asyncio.wait_for(
                        proc.stdout.readline(), timeout=_TURN_IDLE_TIMEOUT_S
                    )
                except TimeoutError:
                    proc.kill()
                    tail = await _stderr_tail(proc)
                    yield {
                        "kind": "error",
                        "detail": (
                            f"Claude Code produced no output for {_TURN_IDLE_TIMEOUT_S:.0f}s "
                            f"and was aborted.{tail}"
                        ),
                    }
                    return
                if not line:
                    break
                for ev in parse_stream([line.decode()]):
                    saw_result = saw_result or ev["kind"] == "result"
                    yield ev
            # The stream can end without a `result` (crash, auth failure, killed
            # subprocess) — silence here used to reach the user as an empty
            # answer with no explanation.
            tail = await _stderr_tail(proc)
            await proc.wait()
            if proc.returncode != 0:
                yield {
                    "kind": "error",
                    "detail": f"Claude Code exited with code {proc.returncode}.{tail}",
                }
            elif not saw_result:
                yield {
                    "kind": "error",
                    "detail": f"Claude Code ended its stream without a result.{tail}",
                }
        finally:
            if proc.returncode is None:
                proc.kill()
            await proc.wait()
