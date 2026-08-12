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
    "mcp__datacharter__list_metrics",
    "mcp__datacharter__query_metric",
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
_JUDGE_TIMEOUT_S = 120.0  # a text-only grading call should finish well within this
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


def claude_version() -> str | None:
    """`claude --version` output, logged at connect so a behavior drift after a
    Claude Code update is attributable instead of a mystery."""
    binary = find_claude()
    if not binary:
        return None
    import subprocess

    try:
        out = subprocess.run(
            [binary, "--version"], capture_output=True, text=True, timeout=15
        )
        return (out.stdout or out.stderr).strip().splitlines()[0] or None
    except Exception:  # noqa: BLE001 — version is diagnostics, never a blocker
        return None


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
    seen_tools: set[str] = set()

    def tool_call(block: dict) -> dict | None:
        name = str(block.get("name", ""))
        if not name.startswith("mcp__datacharter__"):
            return None
        key = block.get("id") or f"{name}:{json.dumps(block.get('input'), sort_keys=True)}"
        if key in seen_tools:
            return None
        seen_tools.add(key)
        return {
            "kind": "tool_call",
            "tool": name.removeprefix("mcp__datacharter__"),
            "sql": (block.get("input") or {}).get("sql") or "",
        }

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
        elif mtype == "assistant":
            # Complete tool inputs arrive here — the streamed content_block_start
            # carries `input: {}`, so relying on stream events alone loses the
            # SQL (shipped: no query chip ever rendered on real CC turns).
            for block in (m.get("message") or {}).get("content", []) or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    ev = tool_call(block)
                    if ev:
                        yield ev
        elif mtype == "stream_event":
            ev = m.get("event", {}) or {}
            if ev.get("type") == "tool_use":  # legacy stream shape
                call = tool_call(ev)
                if call:
                    yield call
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
from the results. When a certified metric matches the question, call \
query_metric instead of writing SQL (see list_metrics). PII columns come back \
masked as ••• — never guess at masked values."""


_ACCESS_CHANGED_NOTE = (
    "\n\nIMPORTANT — data-access permissions changed since your previous tool "
    "calls in this conversation. Earlier query results are now STALE and may show "
    "masked (•••) values that are now visible (or the reverse). Before "
    "answering, you MUST re-run the relevant query with your tools; do NOT reuse, "
    "cite, or trust any earlier tool output."
)


def system_context(guides: str | None, access_changed: bool = False) -> str:
    """The full --append-system-prompt: agent framing plus workspace guides. When
    `access_changed`, append a directive that forces a re-query, so a governance
    change made mid-conversation takes effect without dropping the chat context."""
    base = AGENT_FRAMING + "\n\n# Workspace guides\n" + guides if guides else AGENT_FRAMING
    return base + _ACCESS_CHANGED_NOTE if access_changed else base


async def run_turn(
    question: str,
    serve_url: str,
    session_id: str | None = None,
    dc_bin: str | None = None,
    deny: list[str] | None = None,
    context: str | None = None,
    model: str | None = None,
) -> AsyncIterator[dict]:
    """Run one chat turn; yield parsed stream events. Resumes `session_id` for context.
    `deny` is the effective deny-list from the connect-time assertion; `context` is
    workspace-guide text appended to the system prompt. `model` pins the model (an
    alias like `sonnet`/`opus` or a full id) — used by the eval runner to fix the
    agent-under-test; chat leaves it None to use the account default."""
    dc_bin = dc_bin or _dc_bin()
    with tempfile.TemporaryDirectory(prefix="dc-claude-") as td:
        settings, mcp = build_configs(serve_url, dc_bin, Path(td), deny)
        args = [
            find_claude() or "claude", "-p", question, "--output-format", "stream-json",
            "--verbose", "--include-partial-messages",
            *_base_flags(settings, mcp),
        ]
        if model:
            args += ["--model", model]
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


def _judge_configs(tmpdir: Path) -> tuple[Path, Path]:
    """Locked-down config for a text-only grader: no MCP servers, all built-ins
    denied. The judge grades supplied text — it must reach neither data nor disk."""
    settings = tmpdir / "settings.json"
    mcp = tmpdir / "mcp.json"
    settings.write_text(
        json.dumps({"defaultMode": "dontAsk", "permissions": {"allow": [], "deny": _DENY}})
    )
    mcp.write_text(json.dumps({"mcpServers": {}}))
    return settings, mcp


async def grade(prompt: str, model: str | None = None, system: str | None = None) -> str:
    """One-shot Claude with NO data tools — returns the final result text.

    Used as the eval judge: a separate, stronger model than the agent-under-test,
    graded purely on the text handed to it. Locked down like the probe so the
    grader can't touch the filesystem or the governed data plane."""
    with tempfile.TemporaryDirectory(prefix="dc-judge-") as td:
        settings, mcp = _judge_configs(Path(td))
        args = [
            find_claude() or "claude", "-p", prompt,
            "--output-format", "stream-json", "--verbose",
            *_base_flags(settings, mcp),
        ]
        if model:
            args += ["--model", model]
        if system:
            args += ["--append-system-prompt", system]
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=_env()
        )
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=_JUDGE_TIMEOUT_S)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return ""
        text = ""
        for ev in parse_stream(out.decode().splitlines()):
            if ev["kind"] == "result" and not ev.get("is_error"):
                text = ev.get("text", "")
        return text
