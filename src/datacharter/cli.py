"""Command-line entrypoint: init (workspace scaffolding), serve, secrets."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from datacharter import __version__
from datacharter.agent.llm import LLMClient
from datacharter.demo import TOUR_CHARTER, write_demo_data

CHARTER_TEMPLATE = """\
# DataCharter workspace — https://github.com/datacharter/datacharter
# Sources are data contracts: connection shape here, secrets NEVER here.
# Credentials must be ${NAME} references resolved from your environment,
# .env, or the OS keyring (`datacharter secrets set NAME`).
version: 1

# canary: on   # plant masked honeytokens that alarm if masking ever fails

sources: {}
"""

GUIDE_TEMPLATE = """\
<!-- Workspace guides: the context you'd explain to a colleague, served to agents.
     Every guides/*.md file is loaded (alphabetically) into the agent's context —
     the built-in chat, Claude Code, and any MCP client all receive it.
     Delete this comment and describe YOUR data. Examples of what belongs here:
     - "revenue means amount net of refunds; use orders.amount, not gross_amount"
     - "test accounts have region = 'ZZ'; exclude them from any customer count"
     - "order_date is when the order was placed; created_at is a system timestamp" -->
"""

DEMO_CHARTER = """\
# DataCharter demo workspace. Run: datacharter serve
version: 1

# One contract, many tables: the `store` database groups customers and orders,
# so the sidebar reads store -> table -> columns.
sources:
  store:
    type: sqlite
    path: demo/store.db
    tables: [customers, orders]
    pii:
      customers: [email]

# A governed metric. Try: datacharter metric revenue --grain month
metrics:
  revenue:
    relation: store.orders
    expression: round(sum(total), 2)
    dimensions: [customer_id]
    time_column: placed_on
"""

ENV_EXAMPLE = """\
# Copy to .env and fill in real values. .env is gitignored.
# EXAMPLE_DB_PASSWORD=change-me
"""

GITIGNORE_BLOCK = """\
# DataCharter local state (never commit)
.env
.datacharter/
"""


def _open_engine(workspace: Path, sources: list):
    """Start an engine that opens the local state DB with the same key `serve` uses."""
    from datacharter.engine.session import Engine
    from datacharter.engine.statekey import resolve_state_key

    return Engine(workspace, sources, local_key=resolve_state_key()).start()


def _cmd_init(args: argparse.Namespace) -> int:
    ws = Path(args.directory).resolve()
    ws.mkdir(parents=True, exist_ok=True)
    charter = ws / "charter.yaml"
    if charter.exists() and not args.force:
        print(f"charter.yaml already exists in {ws} (use --force to overwrite).")
        return 1

    tour = args.demo and getattr(args, "tour", False)
    charter.write_text((TOUR_CHARTER if tour else DEMO_CHARTER) if args.demo else CHARTER_TEMPLATE)
    (ws / ".env.example").write_text(ENV_EXAMPLE)
    (ws / "queries").mkdir(exist_ok=True)
    (ws / "guides").mkdir(exist_ok=True)
    guide = ws / "guides" / "overview.md"
    if not guide.exists():
        guide.write_text(GUIDE_TEMPLATE)
    _ensure_gitignore(ws)
    if args.demo:
        write_demo_data(ws, seed_tour=tour)
    print(f"Workspace initialized in {ws}.")
    if args.demo:
        print("Demo data in demo/ — try: datacharter serve")
    return 0


def _ensure_gitignore(ws: Path) -> None:
    gi = ws / ".gitignore"
    existing = gi.read_text() if gi.exists() else ""
    if ".datacharter/" not in existing:
        joiner = "\n" if existing and not existing.endswith("\n") else ""
        gi.write_text(existing + joiner + GITIGNORE_BLOCK)


def _resolve_serve_workspace(directory: str) -> Path:
    """Workspace for serve; ephemeral demo when no charter.yaml (D3, no surprise writes)."""
    ws = Path(directory).resolve()
    if (ws / "charter.yaml").exists():
        return ws
    import tempfile

    demo_ws = Path(tempfile.mkdtemp(prefix="datacharter-demo-"))
    (demo_ws / "charter.yaml").write_text(TOUR_CHARTER)
    write_demo_data(demo_ws, seed_tour=True)
    print(f"No charter.yaml in {ws} — serving an ephemeral demo workspace ({demo_ws}).")
    print("Run `datacharter init` here to start a real workspace.")
    return demo_ws


LOCAL_BASE_URL = "http://127.0.0.1:11434/v1"
LOCAL_DEFAULT_MODEL = "qwen3:8b"


def _local_llm(model: str | None):
    """Point the agent at a local Ollama; verify it's reachable, hint if not."""
    import httpx

    from datacharter.agent.llm import LLMClient

    chosen = model or LOCAL_DEFAULT_MODEL
    try:
        httpx.get("http://127.0.0.1:11434/api/tags", timeout=2.0).raise_for_status()
    except Exception:
        print("Ollama not reachable at 127.0.0.1:11434.")
        print("Install from https://ollama.com, then: ollama pull " + chosen)
        print("Serving without a local agent (the UI still works; chat will be disabled).")
        return None
    print(f"Local agent: Ollama model '{chosen}'. Pull it with: ollama pull {chosen}")
    return LLMClient(base_url=LOCAL_BASE_URL, api_key="ollama", model=chosen)


def _print_attestation(workspace: Path, host: str, port: int) -> None:
    import datetime
    import json

    started = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    note = (
        "File sources stay local; any explicitly-configured remote source "
        "(s3/gcs/azure, attached databases) still connects to its host."
    )
    from datacharter.server.security import LOOPBACK_HOSTS

    loopback_only = host.lower() in LOOPBACK_HOSTS
    record = {
        "mode": "offline",
        "started": started,
        "bind": f"{host}:{port}",
        "loopback_only": loopback_only,
        "llm": "disabled",
        "note": note,
    }
    state = workspace / ".datacharter"
    state.mkdir(parents=True, exist_ok=True)
    (state / "attestation.json").write_text(json.dumps(record, indent=2))
    print("OFFLINE MODE — no-egress attestation")
    print(f"  started: {started}")
    bind_note = "localhost only" if loopback_only else "⚠ REACHABLE ON THE NETWORK (not loopback)"
    print(f"  bind:    {host}:{port} ({bind_note})")
    print("  LLM agent: DISABLED — no data is sent to any model endpoint")
    print(f"  note: {note}")
    print("  written to .datacharter/attestation.json")


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from datacharter.server import create_app

    ws = _resolve_serve_workspace(args.directory)
    llm = None if args.offline else (_local_llm(args.model) if args.local else None)
    app = create_app(
        ws, allow_spill=not args.no_spill, llm=llm, host=args.host, port=args.port,
        offline=args.offline,
    )
    if args.offline:
        _print_attestation(ws, args.host, args.port)
    # flush: under nohup/CI redirection stdout is block-buffered and uvicorn.run
    # never returns, so an unflushed banner leaves the log empty.
    print(f"DataCharter serving {ws} on http://{args.host}:{args.port}", flush=True)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


def _cmd_secrets(args: argparse.Namespace) -> int:
    import getpass

    from datacharter.contracts import secrets as secretstore

    if args.action == "set":
        value = args.value
        if value is None:
            value = getpass.getpass(f"Value for {args.name}: ")
        if not value:
            print("No value provided; nothing stored.", file=sys.stderr)
            return 1
        try:
            secretstore.store_secret(args.name, value)
        except Exception as exc:
            print(f"Could not store secret (no keyring backend?): {exc}", file=sys.stderr)
            return 1
        print(f"Stored '{args.name}' in the OS keyring.")
        return 0
    if args.action == "rm":
        secretstore.delete_secret(args.name)
        print(f"Removed '{args.name}'.")
        return 0
    names = secretstore.list_secrets()
    if names:
        print("\n".join(names))
    else:
        print("No secrets stored via datacharter (env and .env are not listed here).")
    return 0


def _cmd_mcp(args: argparse.Namespace) -> int:
    import asyncio

    from datacharter.mcp.server import serve_stdio

    if args.serve_url:
        from datacharter.agent.remote_tools import RemoteToolBox

        print(f"datacharter MCP proxy → {args.serve_url}", file=sys.stderr)
        asyncio.run(serve_stdio(RemoteToolBox(args.serve_url)))
        return 0


    from datacharter.contracts import load_charter

    ws = Path(args.directory).resolve()
    if not (ws / "charter.yaml").exists():
        print(f"No charter.yaml in {ws}. Run `datacharter init` first.", file=sys.stderr)
        return 1
    from datacharter.agent.factory import build_toolbox, detect_auto_pii
    from datacharter.audit import FlightRecorder
    from datacharter.audit.canary import ensure_canaries

    charter = load_charter(ws)
    engine = _open_engine(ws, charter.sources)
    # F-5: this path shipped without auto_pii/local_access — external MCP
    # clients received value-detected PII unmasked. The factory makes that
    # omission impossible.
    toolbox = build_toolbox(
        engine, charter, auto_pii=asyncio.run(detect_auto_pii(engine)),
        recorder=FlightRecorder(ws, enabled=charter.audit_enabled),
        canary=ensure_canaries(ws, engine, charter.canary_mode),
    )
    # stdout is the MCP protocol channel; diagnostics go to stderr.
    print(f"datacharter MCP server on stdio ({ws})", file=sys.stderr)
    try:
        asyncio.run(serve_stdio(toolbox))
    finally:
        engine.close()
    return 0


def _cmd_diff(args: argparse.Namespace) -> int:
    import asyncio

    from datacharter.contracts import load_charter
    from datacharter.engine.session import EngineError

    ws = Path(args.directory).resolve()
    if not (ws / "charter.yaml").exists():
        print(f"No charter.yaml in {ws}. Run `datacharter init` first.", file=sys.stderr)
        return 1
    charter = load_charter(ws)
    key = [k.strip() for k in args.key.split(",")] if args.key else None
    engine = _open_engine(ws, charter.sources)
    try:
        result = asyncio.run(engine.diff(args.left, args.right, key=key))
    except EngineError as exc:
        print(f"Diff failed: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.close()
    print(f"{args.left}  vs  {args.right}")
    print(f"  only in {args.left}: {result.left_only_count:,}")
    print(f"  only in {args.right}: {result.right_only_count:,}")
    print(f"  in both: {result.common_count:,}")
    if result.changed_count is not None:
        print(f"  changed (same key, different values): {result.changed_count:,}")
    return 0


async def _scan_pii(engine) -> dict[str, list[str]]:
    """Suggest PII columns per relation: by name, then by sampled values."""
    from datacharter.contracts.pii import detect_pii

    return await detect_pii(engine)


def _cmd_scan(args: argparse.Namespace) -> int:
    import asyncio

    from datacharter.contracts import load_charter

    ws = Path(args.directory).resolve()
    if not (ws / "charter.yaml").exists():
        print(f"No charter.yaml in {ws}. Run `datacharter init` first.", file=sys.stderr)
        return 1
    charter = load_charter(ws)
    engine = _open_engine(ws, charter.sources)
    try:
        suggestions = asyncio.run(_scan_pii(engine))
    finally:
        engine.close()
    if not suggestions:
        print("No likely-PII columns detected. Review your columns manually.")
    elif args.write:
        rc = _write_pii(ws, charter, suggestions)
        if rc:
            return rc
    else:
        print("# Suggested PII columns (heuristic — review before adding to charter.yaml):")
        for relation, cols in sorted(suggestions.items()):
            print(f"{relation}:")
            for col in cols:
                print(f"  - {col}")
    return _report_guide_pii(ws, charter, args.strict)


def _report_guide_pii(workspace: Path, charter, strict: bool) -> int:
    """Flag literal PII in guides/*.md and per-table context (agents read those)."""
    from datacharter.contracts.guides import find_pii_in_text, scan_guides_for_pii

    guide_hits = scan_guides_for_pii(workspace)
    context_hits: dict[str, list[str]] = {}
    for s in charter.sources:
        for tbl, txt in s.table_context.items():
            found = find_pii_in_text(txt)
            if found:
                context_hits[f"{s.name}.{tbl} (context)"] = found
    if not guide_hits and not context_hits:
        return 0
    print("\n⚠ Literal PII in guide/context text (agents see this — remove or redact):")
    for name, hits in sorted(guide_hits.items()):
        print(f"  guides/{name}.md:")
        for h in hits:
            print(f"    - {h}")
    for name, hits in sorted(context_hits.items()):
        print(f"  {name}:")
        for h in hits:
            print(f"    - {h}")
    return 1 if strict else 0


def _write_pii(workspace: Path, charter, suggestions: dict) -> int:
    from datacharter.contracts.writer import ContractWriteError, set_pii

    names = {s.name for s in charter.sources}
    skipped = []
    for relation, cols in sorted(suggestions.items()):
        parts = relation.split(".")
        source, table = (parts[0], parts[-1]) if len(parts) > 1 else (relation, relation)
        if source not in names:
            skipped.append(relation)
            continue
        try:
            set_pii(workspace, source, table, cols)
            print(f"charter.yaml: {source}.{table} pii += {', '.join(cols)}")
        except ContractWriteError as exc:
            print(f"Skipped {relation}: {exc}", file=sys.stderr)
            skipped.append(relation)
    if skipped:
        print(f"Not written (no matching charter source): {', '.join(skipped)}", file=sys.stderr)
    return 0


def _valid_name(name: str) -> bool:
    return bool(name) and all(ch.isalnum() or ch == "_" for ch in name)


def _is_relation(name: str) -> bool:
    parts = name.split(".")
    return 1 <= len(parts) <= 3 and all(
        p and all(c.isalnum() or c == "_" for c in p) for p in parts
    )


def _cmd_snapshot(args: argparse.Namespace) -> int:
    from datacharter.contracts import load_charter
    from datacharter.engine.session import EngineError

    ws = Path(args.directory).resolve()
    if not (ws / "charter.yaml").exists():
        print(f"No charter.yaml in {ws}. Run `datacharter init` first.", file=sys.stderr)
        return 1
    if not _valid_name(args.name):
        print(f"Invalid snapshot name: {args.name!r}", file=sys.stderr)
        return 1
    charter = load_charter(ws)
    engine = _open_engine(ws, charter.sources)
    try:
        engine.snapshot_sync(args.sql, args.name)
    except EngineError as exc:
        print(f"Snapshot failed: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.close()
    snapshots = ws / ".datacharter" / "snapshots"
    snapshots.mkdir(parents=True, exist_ok=True)
    (snapshots / f"{args.name}.sql").write_text(args.sql)
    print(f"Saved snapshot 'local.{args.name}'. Re-check with: datacharter recheck {args.name}")
    return 0


def _cmd_recheck(args: argparse.Namespace) -> int:
    import asyncio

    from datacharter.contracts import load_charter
    from datacharter.engine.session import EngineError

    ws = Path(args.directory).resolve()
    if not _valid_name(args.name):
        print(f"Invalid snapshot name: {args.name!r}", file=sys.stderr)
        return 1
    sql_file = ws / ".datacharter" / "snapshots" / f"{args.name}.sql"
    if not sql_file.exists():
        print(
            f"No snapshot 'local.{args.name}'. Create one with "
            f"`datacharter snapshot {args.name} <sql>` first.",
            file=sys.stderr,
        )
        return 1
    sql = sql_file.read_text()
    charter = load_charter(ws)
    engine = _open_engine(ws, charter.sources)
    tmp = f"_recheck_{args.name}"
    try:
        engine.query_sync(f"CREATE OR REPLACE TABLE local.{tmp} AS {sql}")
        result = asyncio.run(engine.diff(f"local.{args.name}", f"local.{tmp}"))
        engine.query_sync(f"DROP TABLE IF EXISTS local.{tmp}")
    except EngineError as exc:
        print(f"Recheck failed: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.close()
    if result.left_only_count == 0 and result.right_only_count == 0:
        print(f"local.{args.name}: unchanged since snapshot.")
        return 0
    print(
        f"local.{args.name}: CHANGED since snapshot — "
        f"{result.left_only_count} row(s) gone, {result.right_only_count} new."
    )
    return 1


def _cmd_drift(args: argparse.Namespace) -> int:
    import asyncio
    import json as _json

    from datacharter.contracts import load_charter
    from datacharter.contracts.pii import classify_pii

    ws = Path(args.directory).resolve()
    if not (ws / "charter.yaml").exists():
        print(f"No charter.yaml in {ws}. Run `datacharter init` first.", file=sys.stderr)
        return 1
    charter = load_charter(ws)
    engine = _open_engine(ws, charter.sources)
    try:
        catalog = asyncio.run(engine.query("SHOW ALL TABLES", timeout_s=30))
    finally:
        engine.close()
    idx = {c: i for i, c in enumerate(catalog.columns)}
    live_columns: dict[str, set[str]] = {}
    fingerprint: dict[str, dict[str, str]] = {}  # relation -> {column: type}
    for row in catalog.rows:
        db = row[idx["database"]]
        if db in ("system", "temp", "local"):
            continue
        name = row[idx["name"]]
        relation = name if db == "memory" else f"{db}.{name}"
        cols = list(row[idx["column_names"]])
        types = list(row[idx["column_types"]])
        fingerprint[relation] = dict(zip(cols, types, strict=False))
        live_columns[name] = set(cols)

    problems: list[str] = []
    # Existence checks: declared tables and PII columns must still be present.
    for src in charter.sources:
        for table in src.tables:
            if table not in live_columns:
                problems.append(
                    f"{src.name}: declared table '{table}' not found in the live source"
                )
        for table, cols in src.pii.items():
            live = live_columns.get(table)
            if live is None:
                problems.append(f"{src.name}: PII table '{table}' not found in the live source")
                continue
            for col in cols:
                if col not in live:
                    problems.append(
                        f"{src.name}: PII column '{table}.{col}' no longer exists (masking gap)"
                    )

    # Shape checks: compare column set/types against a recorded baseline.
    baseline = ws / ".datacharter" / "schema.json"
    if args.update:
        baseline.parent.mkdir(parents=True, exist_ok=True)
        baseline.write_text(_json.dumps(fingerprint, indent=2, sort_keys=True))
        print("Schema baseline updated.")
        return 0
    if not baseline.exists():
        baseline.parent.mkdir(parents=True, exist_ok=True)
        baseline.write_text(_json.dumps(fingerprint, indent=2, sort_keys=True))
    else:
        saved = _json.loads(baseline.read_text())
        for relation, cols in fingerprint.items():
            old = saved.get(relation)
            if old is None:
                continue  # a new relation (e.g. a snapshot) is not drift of a declared source
            for col, typ in cols.items():
                if col not in old:
                    pii = " — looks like PII, add it to charter.yaml" if classify_pii([col]) else ""
                    problems.append(f"{relation}: new column '{col}' ({typ}){pii}")
                elif old[col] != typ:
                    problems.append(f"{relation}: column '{col}' retyped {old[col]} -> {typ}")
            for col in old:
                if col not in cols:
                    problems.append(f"{relation}: column '{col}' removed")

    if not problems:
        print("No schema drift: declared tables/PII present and column shapes unchanged.")
        return 0
    print("Schema drift detected:")
    for problem in problems:
        print(f"  - {problem}")
    return 1


class _GitError(Exception):
    """git could not produce the requested charter version."""


def _git_show_charter(ws: Path, ref: str) -> str | None:
    """Return charter.yaml at a git ref, or None if it did not exist there.

    Raises _GitError when `ws` is not in a git work tree (the caller should then
    tell the user to pass --old explicitly)."""
    import subprocess

    prefix = subprocess.run(
        ["git", "-C", str(ws), "rev-parse", "--show-prefix"],
        capture_output=True, text=True,
    )
    if prefix.returncode != 0:
        raise _GitError(
            f"{ws} is not inside a git repository — pass --old PATH to compare "
            f"against a specific charter file instead of a git version."
        )
    # A bad/typo'd ref must error, not masquerade as "charter didn't exist yet"
    # (which would silently report the whole surface as newly WIDENED).
    verify = subprocess.run(
        ["git", "-C", str(ws), "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
        capture_output=True, text=True,
    )
    if verify.returncode != 0:
        raise _GitError(
            f"git ref {ref!r} could not be resolved. Use a valid ref "
            f"(e.g. --against git:HEAD or git:main~1) or pass --old PATH."
        )
    git_path = f"{prefix.stdout.strip()}charter.yaml"
    show = subprocess.run(
        ["git", "-C", str(ws), "show", f"{ref}:{git_path}"],
        capture_output=True, text=True,
    )
    if show.returncode != 0:
        # Valid ref, but the file was absent there = a brand-new charter; treat
        # the old side as empty (everything is WIDENED).
        return None
    return show.stdout


def _load_charter_text(text: str):
    """Load a charter from raw YAML text (for the git-ref side of a diff)."""
    import tempfile

    from datacharter.contracts import load_charter

    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "charter.yaml").write_text(text)
        return load_charter(tmp, lenient_secrets=True)


def _empty_charter():
    from datacharter.contracts.loader import Charter

    return Charter(version=1, sources=[], warnings=[])


def _cmd_access(args: argparse.Namespace) -> int:
    import json as _json

    from datacharter.contracts import load_charter
    from datacharter.contracts.accessplan import (
        WIDENED,
        diff_surfaces,
        effective_surface,
        render_changes,
        surface_hash,
    )
    from datacharter.contracts.loader import CharterError

    if getattr(args, "access_action", None) != "diff":
        print("usage: datacharter access diff [WORKSPACE] [options]", file=sys.stderr)
        return 1

    ws = Path(args.directory).resolve()
    try:
        new_path = Path(args.new).resolve() if args.new else ws / "charter.yaml"
        if not new_path.exists():
            print(f"No charter.yaml at {new_path}.", file=sys.stderr)
            return 1
        new_charter = load_charter(new_path.parent, new_path.name, lenient_secrets=True)

        if args.old:
            old_path = Path(args.old).resolve()
            if not old_path.exists():
                print(f"No file at {old_path} (--old).", file=sys.stderr)
                return 1
            old_charter = load_charter(old_path.parent, old_path.name, lenient_secrets=True)
        else:
            ref = args.against.split("git:", 1)[-1] if args.against else "HEAD"
            old_text = _git_show_charter(ws, ref)
            old_charter = _load_charter_text(old_text) if old_text is not None \
                else _empty_charter()
    except CharterError as exc:
        print(f"Could not load a charter to diff: {exc}", file=sys.stderr)
        return 1
    except _GitError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    old_s, new_s = effective_surface(old_charter), effective_surface(new_charter)
    changes = diff_surfaces(old_s, new_s)
    widened = [c for c in changes if c.kind == WIDENED]

    if args.json:
        print(_json.dumps({
            "old_hash": surface_hash(old_s),
            "new_hash": surface_hash(new_s),
            "summary": {
                "widened": len(widened),
                "narrowed": sum(1 for c in changes if c.kind != WIDENED),
                "total": len(changes),
            },
            "changes": [{"kind": c.kind, "path": c.path, "detail": c.detail} for c in changes],
        }))
    elif args.md:
        print(_render_access_md(changes))
    else:
        print(render_changes(changes))

    if args.fail_on == "widened" and widened:
        if not args.json and not args.md:
            print(
                f"\n{len(widened)} change(s) widen the agent-visible surface — "
                f"review required (--fail-on widened).",
                file=sys.stderr,
            )
        return 2
    return 0


def _render_access_md(changes) -> str:
    from datacharter.contracts.accessplan import WIDENED

    if not changes:
        return "**Access Plan:** no change to the agent-visible access surface. ✅"
    widened = sum(1 for c in changes if c.kind == WIDENED)
    head = f"**Access Plan:** {widened} widened, {len(changes) - widened} narrowed."
    rows = ["", "| Change | Where | Detail |", "| --- | --- | --- |"]
    rows += [f"| {c.kind} | `{c.path}` | {c.detail} |" for c in changes]
    return head + "\n" + "\n".join(rows)


def _cmd_explain(args: argparse.Namespace) -> int:
    import asyncio

    from datacharter.contracts import load_charter
    from datacharter.engine.guard import QueryNotAllowed
    from datacharter.engine.session import EngineError

    ws = Path(args.directory).resolve()
    if not (ws / "charter.yaml").exists():
        print(f"No charter.yaml in {ws}. Run `datacharter init` first.", file=sys.stderr)
        return 1
    charter = load_charter(ws)
    engine = _open_engine(ws, charter.sources)
    try:
        result = asyncio.run(engine.query(f"EXPLAIN {args.sql}"))
    except (EngineError, QueryNotAllowed) as exc:
        print(f"Explain failed: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.close()
    for row in result.rows:  # EXPLAIN yields (key, plan-text); print the plan
        print(row[-1])
    return 0


def _cmd_sample(args: argparse.Namespace) -> int:
    import asyncio
    import csv

    from datacharter.agent.tools import MASKED
    from datacharter.contracts import load_charter
    from datacharter.engine.session import EngineError

    ws = Path(args.directory).resolve()
    if not (ws / "charter.yaml").exists():
        print(f"No charter.yaml in {ws}. Run `datacharter init` first.", file=sys.stderr)
        return 1
    if not _is_relation(args.relation):
        print(f"Invalid relation name: {args.relation!r}", file=sys.stderr)
        return 1
    charter = load_charter(ws)
    pii = {c.lower() for s in charter.sources for cols in s.pii.values() for c in cols}
    engine = _open_engine(ws, charter.sources)
    try:
        result = asyncio.run(
            engine.query(f"SELECT * FROM {args.relation}", row_limit=args.rows)
        )
    except EngineError as exc:
        print(f"Sample failed: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.close()
    mask = {i for i, c in enumerate(result.columns) if c.lower() in pii}
    writer = csv.writer(sys.stdout)
    writer.writerow(result.columns)
    for row in result.rows:
        writer.writerow(
            [MASKED if i in mask else ("" if v is None else v) for i, v in enumerate(row)]
        )
    return 0


def _cmd_metric(args: argparse.Namespace) -> int:
    import asyncio

    from datacharter.contracts import load_charter
    from datacharter.contracts.metrics import MetricError, metric_sql
    from datacharter.engine.session import EngineError

    ws = Path(args.directory).resolve()
    if not (ws / "charter.yaml").exists():
        print(f"No charter.yaml in {ws}. Run `datacharter init` first.", file=sys.stderr)
        return 1
    charter = load_charter(ws)
    metric = next((m for m in charter.metrics if m.name == args.name), None)
    if metric is None:
        available = ", ".join(m.name for m in charter.metrics) or "(none defined)"
        print(f"No metric '{args.name}'. Available: {available}", file=sys.stderr)
        return 1
    by = [c.strip() for c in args.by.split(",")] if args.by else None
    try:
        sql = metric_sql(metric, by=by, grain=args.grain)
    except MetricError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    engine = _open_engine(ws, charter.sources)
    try:
        result = asyncio.run(engine.query(sql))
    except EngineError as exc:
        print(f"Metric failed: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.close()
    print(" | ".join(result.columns))
    for row in result.rows:
        print(" | ".join("" if v is None else str(v) for v in row))
    return 0


def _cmd_query(args: argparse.Namespace) -> int:
    import csv
    import json as _json

    from datacharter.contracts import load_charter
    from datacharter.engine.guard import QueryNotAllowed
    from datacharter.engine.session import EngineError

    ws = Path(args.directory).resolve()
    if not (ws / "charter.yaml").exists():
        print(f"No charter.yaml in {ws}. Run `datacharter init` first.", file=sys.stderr)
        return 1
    charter = load_charter(ws)
    engine = _open_engine(ws, charter.sources)
    try:
        result = engine.query_sync(args.sql)
    except (EngineError, QueryNotAllowed) as exc:
        print(f"Query failed: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.close()
    if args.format == "json":
        rows = [dict(zip(result.columns, r, strict=True)) for r in result.rows]
        print(_json.dumps(rows, default=str))
    elif args.format == "csv":
        writer = csv.writer(sys.stdout)
        writer.writerow(result.columns)
        writer.writerows(result.rows)
    else:  # table
        print(" | ".join(result.columns))
        for row in result.rows:
            print(" | ".join("" if v is None else str(v) for v in row))
    return 0


def _cmd_dp(args: argparse.Namespace) -> int:
    """Differential-privacy query mode: Laplace-noise an aggregate and spend from a
    per-workspace ε budget. Refuses non-aggregate queries and an exhausted budget."""
    import csv

    from datacharter.contracts import load_charter
    from datacharter.dp import Budget, DPError, is_aggregate, privatize_row
    from datacharter.engine.guard import QueryNotAllowed
    from datacharter.engine.session import EngineError

    ws = Path(args.directory).resolve()
    if not (ws / "charter.yaml").exists():
        print(f"No charter.yaml in {ws}. Run `datacharter init` first.", file=sys.stderr)
        return 1

    budget = Budget.load(ws, args.budget)
    if args.reset:
        budget.reset()
        print(f"Privacy budget reset (cap ε={args.budget}).")
        return 0
    if args.status:
        print(f"Privacy budget: spent ε={budget.spent:.3f} of {budget.cap} "
              f"over {budget.queries} query(ies); {budget.remaining:.3f} left.")
        return 0

    if not is_aggregate(args.sql):
        print("DP mode is for aggregates (COUNT/SUM/… or GROUP BY). This query returns "
              "row-level data, where per-cell noise would leak the rows. Aggregate first.",
              file=sys.stderr)
        return 1
    sensitivity = 1.0 if args.bound is None else float(args.bound)
    non_negative_int = args.bound is None  # COUNT results are non-negative integers
    try:
        budget.check(args.epsilon)
    except DPError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    charter = load_charter(ws)
    engine = _open_engine(ws, charter.sources)
    try:
        result = engine.query_sync(args.sql)
    except (EngineError, QueryNotAllowed) as exc:
        print(f"Query failed: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.close()

    numeric = {
        i for i, _ in enumerate(result.columns)
        if all(r[i] is None or isinstance(r[i], (int, float)) for r in result.rows)
        and any(r[i] is not None for r in result.rows)
    }
    if not numeric:
        print("No numeric aggregate column to privatize in the result.", file=sys.stderr)
        return 1
    budget.spend(args.epsilon)

    writer = csv.writer(sys.stdout)
    writer.writerow(result.columns)
    for row in result.rows:
        writer.writerow(privatize_row(
            list(row), numeric, epsilon=args.epsilon, sensitivity=sensitivity,
            non_negative_int=non_negative_int,
        ))
    print(f"# ε={args.epsilon} spent (Laplace, sensitivity={sensitivity:g}); "
          f"budget {budget.remaining:.3f}/{budget.cap} left", file=sys.stderr)
    return 0


def _cmd_asof(args: argparse.Namespace) -> int:
    """Governance time-travel: reconstruct the agent-visible surface as it was at a
    git ref, and (optionally) run a query masked by *that* charter's PII rules
    against today's data — "what would the agent have seen under last March's rules?"."""
    import csv
    import json as _json

    from datacharter.contracts.accessplan import effective_surface, surface_hash
    from datacharter.contracts.loader import CharterError

    ws = Path(args.directory).resolve()
    ref = args.ref.split("git:", 1)[-1] if args.ref.startswith("git:") else args.ref
    try:
        text = _git_show_charter(ws, ref)
    except _GitError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if text is None:
        print(f"No charter.yaml committed at git ref '{ref}'.", file=sys.stderr)
        return 1
    try:
        ref_charter = _load_charter_text(text)
    except CharterError as exc:
        print(f"Charter at '{ref}' does not parse: {exc}", file=sys.stderr)
        return 1

    if not args.query and not args.relation:
        surface = effective_surface(ref_charter)
        if args.json:
            print(_json.dumps({"ref": ref, "surface_hash": surface_hash(surface),
                               "surface": surface}, indent=2, sort_keys=True))
            return 0
        print(f"Agent-visible surface as of {ref}  (surface_hash {surface_hash(surface)[:12]})")
        for sname, sinfo in surface.get("sources", {}).items():
            print(f"  {sname} ({sinfo.get('type')})")
            for tbl, tinfo in sinfo.get("tables", {}).items():
                masked = ", ".join(tinfo.get("pii") or []) or "—"
                rf = tinfo.get("row_filter")
                extra = f"  row_filter: {rf}" if rf else ""
                print(f"    {tbl}: masked[{masked}]{extra}")
        return 0

    # Query/relation mode: run against current data, mask by the ref charter's PII.
    import asyncio

    from datacharter.agent.tools import MASKED
    from datacharter.contracts import load_charter
    from datacharter.engine.session import EngineError

    if not (ws / "charter.yaml").exists():
        print(f"No charter.yaml in {ws} to reach the data.", file=sys.stderr)
        return 1
    if args.relation and not _is_relation(args.relation):
        print(f"Invalid relation name: {args.relation!r}", file=sys.stderr)
        return 1
    sql = args.query or f"SELECT * FROM {args.relation}"
    pii = {c.lower() for s in ref_charter.sources for cols in s.pii.values() for c in cols}
    engine = _open_engine(ws, load_charter(ws).sources)
    try:
        result = asyncio.run(engine.query(sql, row_limit=args.rows))
    except EngineError as exc:
        print(f"Query failed: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.close()
    mask = {i for i, c in enumerate(result.columns) if c.lower() in pii}
    writer = csv.writer(sys.stdout)
    writer.writerow(result.columns)
    for row in result.rows:
        writer.writerow(
            [MASKED if i in mask else ("" if v is None else v) for i, v in enumerate(row)]
        )
    return 0


def _cmd_monitor(args: argparse.Namespace) -> int:
    """Run the governance gates in one pass and report an aggregate compliance status.

    Each gate is the real command's code (captured), so a green monitor is evidence
    about what actually runs. Exits non-zero if any gate reports a violation."""
    import contextlib
    import io

    from datacharter.compliance import CheckResult, ComplianceReport, render_report

    ws = Path(args.directory).resolve()
    if not (ws / "charter.yaml").exists():
        print(f"No charter.yaml in {ws}. Run `datacharter init` first.", file=sys.stderr)
        return 1

    def _run(fn, ns) -> tuple[bool, str]:
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                rc = fn(argparse.Namespace(**ns))
        except Exception as exc:  # a gate that raises is a failed gate, not a crashed monitor
            return False, f"{type(exc).__name__}: {exc}"
        return rc == 0, buf.getvalue()

    report = ComplianceReport()
    base = {"directory": str(ws)}

    ok, out = _run(_cmd_test, {**base, "select": None})
    report.results.append(CheckResult("contract-tests", ok, out))

    ok, out = _run(_cmd_drift, {**base, "update": False})
    report.results.append(CheckResult("schema-drift", ok, out))

    # Access-plan gate needs a committed baseline; skip cleanly outside a git tree.
    try:
        in_git = _git_show_charter(ws, "HEAD") is not None
    except _GitError:
        in_git = False
    if in_git:
        ok, out = _run(_cmd_access, {
            **base, "access_action": "diff", "against": "git:HEAD", "old": None,
            "new": None, "json": False, "md": False, "fail_on": "widened",
        })
        report.results.append(CheckResult("access-plan", ok, out))
    else:
        report.results.append(CheckResult("access-plan", True, "not a git work tree", skipped=True))

    if not args.no_gauntlet:
        ok, out = _run(_cmd_redteam, {**base})
        report.results.append(CheckResult("gauntlet", ok, out))
    else:
        report.results.append(CheckResult("gauntlet", True, "", skipped=True))

    if args.json:
        print(report.to_json())
    else:
        print(render_report(report))
    return 0 if report.ok else 1


def _cmd_test(args: argparse.Namespace) -> int:
    from datacharter.contracts import load_charter
    from datacharter.contracts.datatests import DataTestError, check_sql
    from datacharter.engine.guard import QueryNotAllowed
    from datacharter.engine.session import EngineError

    ws = Path(args.directory).resolve()
    if not (ws / "charter.yaml").exists():
        print(f"No charter.yaml in {ws}. Run `datacharter init` first.", file=sys.stderr)
        return 1
    charter = load_charter(ws)
    tests = charter.tests
    if args.select:
        tests = [t for t in tests if t.name == args.select]
    if not tests:
        print("No matching tests." if args.select else "No tests declared in charter.yaml.")
        return 0
    engine = _open_engine(ws, charter.sources)
    failures = 0
    try:
        for t in tests:
            try:
                n = engine.query_sync(check_sql(t)).rows[0][0]
            except (DataTestError, EngineError, QueryNotAllowed) as exc:
                print(f"  ✗ {t.name} — error: {exc}")
                failures += 1
                continue
            if n:
                print(f"  ✗ {t.name} — {n} failing row(s)")
                failures += 1
            else:
                print(f"  ✓ {t.name}")
    finally:
        engine.close()
    print(f"\n{len(tests) - failures}/{len(tests)} passed.")
    return 1 if failures else 0


def _cmd_audit(args: argparse.Namespace) -> int:
    from datacharter.audit.evidence import export_pack, read_entries, verify_chain

    action = None
    directory = "."
    for tok in args.tokens:
        if tok in ("verify", "export", "show") and action is None:
            action = None if tok == "show" else tok
        else:
            directory = tok
    ws = Path(directory).resolve()
    if not (ws / "charter.yaml").exists():
        print(f"No charter.yaml in {ws}. Run `datacharter init` first.", file=sys.stderr)
        return 1
    if action == "verify":
        ok, n, detail = verify_chain(ws)
        if not ok:
            print(detail, file=sys.stderr)
            return 1
        if n == 0:
            # Empty/absent is its own exit code: a deleted log must never
            # look like a verified one to scripted auditors.
            print(f"⚠ {detail}", file=sys.stderr)
            return 2
        print(f"{detail} ✓")
        return 0

    if action == "export":
        from datetime import UTC, datetime

        out = Path(args.out) if args.out else ws / (
            f"audit-evidence-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}.zip"
        )
        path = export_pack(ws, out, since=args.since, until=args.until)
        print(f"Evidence pack written: {path}")
        return 0

    # default: show recent sessions with access summaries
    entries = read_entries(ws)
    if not entries:
        print("No audit entries yet. Agent access is recorded automatically.")
        return 0
    sessions: dict[str, dict] = {}
    order: list[str] = []
    for e in entries:
        if e.get("type") == "session":
            sessions[e["session"]] = {"meta": e, "accesses": 0, "errors": 0, "last": e["ts"]}
            order.append(e["session"])
        elif e.get("type") == "access" and e.get("session") in sessions:
            s = sessions[e["session"]]
            s["accesses"] += 1
            s["errors"] += 1 if e.get("error") else 0
            s["last"] = e["ts"]
    ok, n, detail = verify_chain(ws)
    print(f"Audit log: {detail}" + (" ✓" if ok else "  ⚠ BROKEN"))
    for sid in reversed(order[-20:]):
        s = sessions[sid]
        m = s["meta"]
        who = (m.get("client") or {}).get("name") or m.get("model") or m["surface"]
        q = f'  "{m["question"]}"' if m.get("question") else ""
        err = f"  ({s['errors']} errors)" if s["errors"] else ""
        print(f"  {m['ts'][:16]}  [{m['surface']}] {who} · {m['user']} · "
              f"{s['accesses']} accesses{err}{q}")
    return 0


def _cmd_suggest(args: argparse.Namespace) -> int:
    from datacharter.contracts.suggest import apply_suggestions, mine_history, render_suggestions

    ws = Path(args.directory).resolve()
    if not (ws / "charter.yaml").exists():
        print(f"No charter.yaml in {ws}. Run `datacharter init` first.", file=sys.stderr)
        return 1
    suggestions = mine_history(ws)
    print(render_suggestions(suggestions))
    if args.apply and suggestions:
        path = apply_suggestions(ws, suggestions)
        print(f"\nAppended {len(suggestions)} suggestion(s) to {path.relative_to(ws)}.")
        print("Edit the file to refine the wording — it's a guide like any other.")
    return 0


def _cmd_canary(args: argparse.Namespace) -> int:
    from datacharter.audit import FlightRecorder
    from datacharter.audit.canary import ensure_canaries
    from datacharter.contracts import load_charter

    action = None
    directory = "."
    for tok in args.tokens:
        if tok in ("drill", "status") and action is None:
            action = None if tok == "status" else tok
        else:
            directory = tok
    ws = Path(directory).resolve()
    if not (ws / "charter.yaml").exists():
        print(f"No charter.yaml in {ws}. Run `datacharter init` first.", file=sys.stderr)
        return 1
    charter = load_charter(ws)

    if charter.canary_mode is None:
        print(
            "Canary tripwires: DISABLED.\n"
            "  Canaries plant synthetic honeytokens in a masked local table\n"
            "  (local.canaries). If a token ever appears in agent output, masking\n"
            "  provably failed — an alarm lands in the audit chain.\n"
            "  Enable with `canary: on` (block mode) or `canary: {mode: log}`\n"
            "  in charter.yaml."
        )
        return 1 if action == "drill" else 0

    engine = _open_engine(ws, charter.sources)
    try:
        guard = ensure_canaries(ws, engine, charter.canary_mode)
    finally:
        engine.close()
    if guard is None:
        print("Canary planting failed — check the workspace state.", file=sys.stderr)
        return 1

    if action == "drill":
        recorder = FlightRecorder(ws, enabled=charter.audit_enabled)
        recorder.start_session("drill", question="canary drill (deliberate tripwire test)")
        fake_result = (
            '{"columns": ["email"], "rows": [["' + guard.tokens[0]
            + '@tripwire.invalid"]], "row_count": 1, "truncated": false}'
        )
        hit = guard.scan(fake_result)
        if hit is None:
            print("Drill FAILED: guard did not detect its own token.", file=sys.stderr)
            return 1
        recorder.record_alarm("query", '{"sql": "-- canary drill"}', hit)
        blocked = " (block mode would withhold the response)" if guard.mode == "block" else ""
        print(f"Drill OK: token detected and alarm recorded in the audit chain{blocked}.")
        print("See it with: datacharter audit " + (directory if directory != "." else ""))
        return 0

    print(f"Canary tripwires: ARMED ({guard.mode} mode), {len(guard.tokens)} tokens "
          f"planted in local.canaries.")
    return 0


def _cmd_redteam(args: argparse.Namespace) -> int:
    import asyncio

    from datacharter.agent.factory import build_toolbox, detect_auto_pii
    from datacharter.agent.redteam import render_report, run_gauntlet
    from datacharter.audit import FlightRecorder
    from datacharter.audit.canary import ensure_canaries
    from datacharter.contracts import load_charter

    ws = Path(args.directory).resolve()
    if not (ws / "charter.yaml").exists():
        print(f"No charter.yaml in {ws}. Run `datacharter init` first.", file=sys.stderr)
        return 1
    charter = load_charter(ws)
    engine = _open_engine(ws, charter.sources)
    try:
        # Force-plant sentinels even if the user's canary is off — the Gauntlet
        # needs bait to prove masking holds (local.canaries stays hidden from
        # list_tables regardless).
        guard = ensure_canaries(ws, engine, charter.canary_mode or "log")
        if guard is None:
            print("Could not plant honeytokens for the Gauntlet.", file=sys.stderr)
            return 1
        recorder = FlightRecorder(ws, enabled=charter.audit_enabled)
        recorder.start_session("redteam", question="the Gauntlet (governance self-attack)")
        toolbox = build_toolbox(
            engine, charter,
            auto_pii=asyncio.run(detect_auto_pii(engine)),
            recorder=recorder, canary=guard,
        )
        report = asyncio.run(
            run_gauntlet(toolbox, guard, policies_active=bool(charter.policies))
        )
    finally:
        engine.close()
    print(render_report(report))
    print("\nRecorded to the flight recorder. Re-run in CI: `datacharter redteam` "
          "(exit 1 on any breach).")
    return 0 if report.ok else 1


def _cmd_demo(args: argparse.Namespace) -> int:
    from datacharter.agent import demo

    return demo.run(args.directory)


def _cmd_connect(args: argparse.Namespace) -> int:
    from datacharter.agent import connect

    return connect.run(args.directory, args.client, args.serve_url)


def _cmd_import_dbt(args: argparse.Namespace) -> int:
    from datacharter.contracts import load_charter
    from datacharter.contracts.dbt_import import import_manifest

    manifest = Path(args.manifest)
    if not manifest.exists():
        print(f"No such manifest: {manifest}", file=sys.stderr)
        return 1
    try:
        text, summary = import_manifest(str(manifest))
    except (ValueError, KeyError, TypeError) as exc:
        print(f"Could not parse dbt manifest {manifest}: {exc}", file=sys.stderr)
        return 1
    if summary["sources"] == 0:
        print("No models or sources found in the manifest — nothing to import.", file=sys.stderr)
        return 1

    out = Path(args.out) if args.out else Path.cwd() / "charter.yaml"
    if out.exists() and not args.force:
        print(f"{out} exists; use --force to overwrite or -o to write elsewhere.", file=sys.stderr)
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)

    warn = ""
    try:  # a scaffold that won't load is a bug worth catching here, not at serve time
        load_charter(out.parent, out.name, lenient_secrets=True)
    except Exception as exc:  # noqa: BLE001
        warn = f"\n  ⚠ the generated charter did not validate: {exc}"

    unmapped = "  (unmapped adapter — verify the type)" if summary["unmapped_adapter"] else ""
    print(f"Wrote {out}")
    print(f"  adapter {summary['adapter'] or 'unknown'} → type {summary['source_type']}{unmapped}")
    print(f"  {summary['sources']} source(s) · {summary['tables']} table(s) · "
          f"{summary['pii_columns']} PII column(s) detected")
    print("  Next: fill in each source's connection + ${ENV} credentials, then "
          "`datacharter scan` / `datacharter serve`.")
    if warn:
        print(warn, file=sys.stderr)
    return 0


def _cmd_import_odcs(args: argparse.Namespace) -> int:
    from datacharter.contracts import load_charter
    from datacharter.contracts.odcs import import_odcs_file

    src = Path(args.contract)
    if not src.exists():
        print(f"No such contract: {src}", file=sys.stderr)
        return 1
    try:
        text, summary = import_odcs_file(str(src))
    except (ValueError, KeyError, TypeError) as exc:
        print(f"Could not parse ODCS contract {src}: {exc}", file=sys.stderr)
        return 1
    if summary["tables"] == 0:
        print("No tables found in the contract's schema — nothing to import.", file=sys.stderr)
        return 1

    out = Path(args.out) if args.out else Path.cwd() / "charter.yaml"
    if out.exists() and not args.force:
        print(f"{out} exists; use --force to overwrite or -o to write elsewhere.", file=sys.stderr)
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)

    warn = ""
    try:
        load_charter(out.parent, out.name, lenient_secrets=True)
    except Exception as exc:  # noqa: BLE001
        warn = f"\n  ⚠ the generated charter did not validate: {exc}"
    unmapped = "  (unmapped server type — verify)" if summary["unmapped_type"] else ""
    print(f"Wrote {out}")
    print(f"  server type → {summary['source_type']}{unmapped}")
    print(f"  1 source · {summary['tables']} table(s) · {summary['pii_columns']} PII column(s)")
    print("  Next: fill the connection + ${ENV} credentials, then "
          "`datacharter scan` / `datacharter serve`.")
    if warn:
        print(warn, file=sys.stderr)
    return 0


def _cmd_export_odcs(args: argparse.Namespace) -> int:
    from datacharter.contracts import load_charter
    from datacharter.contracts.odcs import export_odcs_yaml

    ws = Path(args.directory).resolve()
    if not (ws / "charter.yaml").exists():
        print(f"No charter.yaml in {ws}. Run `datacharter init` first.", file=sys.stderr)
        return 1
    charter = load_charter(ws, lenient_secrets=True)
    text = export_odcs_yaml(charter)
    if args.out:
        Path(args.out).write_text(text)
        print(f"Wrote {args.out} — ODCS DataContract "
              f"({len(charter.sources)} server(s), "
              f"{sum(len(s.tables) for s in charter.sources)} table(s)).")
    else:
        print(text)
    return 0


def _cmd_eval(args: argparse.Namespace) -> int:
    import asyncio

    from datacharter.agent.eval_runner import run_suite
    from datacharter.contracts import load_charter
    from datacharter.contracts.evals import EvalError, load_suites

    ws = Path(args.directory).resolve()
    if not (ws / "charter.yaml").exists():
        print(f"No charter.yaml in {ws}. Run `datacharter init` first.", file=sys.stderr)
        return 1

    if args.history:
        return _eval_history(ws)

    charter = load_charter(ws)
    try:
        suites = load_suites(ws)
    except EvalError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.suite:
        suites = [s for s in suites if s.name == args.suite]
    if not suites:
        print("No eval suites in evals/*.yaml.", file=sys.stderr)
        return 1

    import os

    # Evals run every question through a real agent. With no endpoint at all,
    # every case fails 0% for a reason the scorecard can't show — refuse with
    # the reason instead.
    if not args.local and not os.environ.get("OPENAI_BASE_URL") and not os.environ.get(
        "OPENAI_API_KEY"
    ):
        print(
            "No agent endpoint configured — evals run each question through a real "
            "agent.\nSet OPENAI_BASE_URL / OPENAI_API_KEY (any OpenAI-compatible "
            "endpoint), or pass --local to use Ollama.",
            file=sys.stderr,
        )
        return 2

    llm = _local_llm(args.model) if args.local else LLMClient()
    engine = _open_engine(ws, charter.sources)
    from datacharter.agent.factory import build_toolbox, detect_auto_pii
    from datacharter.audit import FlightRecorder
    from datacharter.audit.canary import ensure_canaries

    auto_pii = asyncio.run(detect_auto_pii(engine))
    # Audit + canary parity with the server's eval path: eval runs the agent
    # surface, so its accesses must be recorded and its tripwire armed too.
    recorder = FlightRecorder(ws, enabled=charter.audit_enabled)
    canary = ensure_canaries(ws, engine, charter.canary_mode)
    box = build_toolbox(engine, charter, auto_pii=auto_pii, recorder=recorder, canary=canary)
    box_off = (
        build_toolbox(
            engine, charter, auto_pii=auto_pii, recorder=recorder, canary=canary,
            guides_override="",
        )
        if args.compare_guides else None
    )

    from datacharter.agent.llm import LLMError

    worst = 1.0
    errored = 0
    try:
        for suite in suites:
            record = asyncio.run(
                run_suite(
                    suite, box, llm=llm, toolbox_off=box_off,
                    samples=args.samples, judge=args.judge,
                )
            )
            _print_scorecard(record)
            from datacharter.agent.eval_store import save_run

            save_run(ws, record)
            worst = min(worst, record.overall["with_guides"])
            errored += record.overall.get("errored", 0)
    except LLMError as exc:
        print(f"\nAgent endpoint error: {exc}", file=sys.stderr)
        print(
            "Check OPENAI_BASE_URL / OPENAI_API_KEY (or your --local Ollama model).",
            file=sys.stderr,
        )
        return 1
    finally:
        engine.close()

    if errored:
        # An outage is not a scorecard: never exit green when cases errored.
        print(f"\n{errored} case run(s) errored — agent endpoint problem.", file=sys.stderr)
        return 2
    if args.threshold is not None and worst < args.threshold:
        print(f"\nBelow threshold ({worst:.0%} < {args.threshold:.0%}).", file=sys.stderr)
        return 1
    return 0


def _print_scorecard(record) -> None:
    def _mark(outcome) -> str:
        if outcome.error is not None:
            return "⚠"
        return "✓" if outcome.passed else "✗"

    print(f"\nSuite: {record.suite}")
    for case in record.cases:
        mark = _mark(case.with_guides)
        print(f"  {mark} {case.question}")
        if case.with_guides.error is not None:
            print(f"      errored (not evaluated): {case.with_guides.error}")
        if case.without_guides is not None:
            print(f"      guides on: {mark}   guides off: {_mark(case.without_guides)}")
    o = record.overall
    print(f"\n  {o['with_guides']:.0%} passed", end="")
    if "lift" in o:
        print(
            f"  (guides off: {o['without_guides']:.0%}  →  lift: {o['lift']:+.0%})", end=""
        )
    if o.get("errored"):
        print(f"  ⚠ {o['errored']} case run(s) ERRORED — fix the agent endpoint "
              f"before trusting these numbers", end="")
    print()


def _eval_history(ws: Path) -> int:
    from datacharter.agent.eval_store import load_history, regression_diff

    hist = load_history(ws)
    if not hist:
        print("No eval history yet. Run `datacharter eval` first.")
        return 0
    print("Pass rate over time:")
    for run in hist:
        o = run.get("overall", {})
        lift = f"  lift {o['lift']:+.0%}" if "lift" in o else ""
        print(
            f"  {run.get('started_at', '?')}  {o.get('with_guides', 0):.0%}{lift}  "
            f"[{run.get('suite', '?')}]"
        )
    if len(hist) >= 2:
        regressed = regression_diff(hist[-2], hist[-1])
        if regressed:
            print("\nRegressed since the previous run:")
            for q in regressed:
                print(f"  ✗ {q}")
    return 0


def _cmd_openlineage(args: argparse.Namespace) -> int:
    from datacharter import openlineage

    return openlineage.emit(
        args.directory, args.url, namespace=args.namespace, job=args.job, out=args.out
    )


def _cmd_provenance(args: argparse.Namespace) -> int:
    import json as _json

    from datacharter.provenance import keys, receipt, seal_query

    action = args.prov_action
    if action == "keygen":
        try:
            signer = keys.generate(args.directory, force=args.force)
        except keys.ProvenanceKeyError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(f"Signing key created — key_id {signer.key_id}")
        print(f"  public key: {signer.public_hex}")
        print("  Publish this public key so anyone can verify your receipts offline.")
        return 0

    if action == "pubkey":
        pub = keys.load_public(args.directory)
        if pub is None:
            print("No signing key yet. Run `datacharter provenance keygen`.", file=sys.stderr)
            return 1
        print(pub.hex())
        return 0

    if action == "seal":
        try:
            r = seal_query(args.directory, args.sql, model=args.model)
        except (keys.ProvenanceKeyError, ValueError, FileNotFoundError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        text = _json.dumps(r, indent=2)
        if args.out:
            Path(args.out).write_text(text)
            print(f"Wrote {args.out} — receipt {r['content_hash'][:12]} "
                  f"signed by key {r['signature']['key_id']}")
        else:
            print(text)
        return 0

    if action == "verify":
        try:
            r = _json.loads(Path(args.receipt).read_text())
        except (OSError, ValueError) as exc:
            print(f"Could not read receipt: {exc}", file=sys.stderr)
            return 1
        v = receipt.verify(r, expected_pubkey=args.pubkey)
        for name, ok in v["checks"].items():
            print(f"  {'PASS' if ok else 'FAIL'}  {name}")
        overall = v["ok"]
        if args.flight:
            link = receipt.verify_audit_link(r, args.flight)
            link_ok = link["chain_ok"] and link["head_in_chain"]
            print(f"  {'PASS' if link_ok else 'FAIL'}  audit_link  ({link['detail']})")
            overall = overall and link_ok
        body = r.get("body") or {}
        q = str(body.get("question") or "")
        print(f"\n  key_id {v['key_id']}  ·  model {body.get('model')}  ·  {q[:60]}")
        print("VERIFIED" if overall else "NOT VERIFIED")
        return 0 if overall else 1

    print("Usage: datacharter provenance [keygen|pubkey|seal|verify]", file=sys.stderr)
    return 1


def _cmd_lineage(args: argparse.Namespace) -> int:
    import json as _json

    from datacharter.engine import history

    ws = Path(args.directory).resolve()
    graph = history.lineage(ws)
    if args.relation:
        rel = args.relation
        graph = {
            "relations": {rel: graph["relations"].get(rel, {"co_read": {}})},
            "columns": {c: ins for c, ins in graph["columns"].items() if rel in " ".join(ins)},
        }
    if args.json:
        print(_json.dumps(graph, indent=2))
        return 0
    if not graph["relations"] and not graph["columns"]:
        print("No query history yet. Run some queries in the app first.")
        return 0
    for rel, node in sorted(graph["relations"].items()):
        print(rel)
        for other, n in sorted(node["co_read"].items(), key=lambda kv: -kv[1]):
            print(f"  read with {other} ({n} quer{'y' if n == 1 else 'ies'})")
    derived = {c: ins for c, ins in graph["columns"].items() if ins}
    if derived:
        print("\ncolumn lineage:")
        for out_col, inputs in sorted(derived.items()):
            print(f"  {out_col} <- {', '.join(inputs)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="datacharter", description="Charter your data.")
    parser.add_argument("--version", action="version", version=f"datacharter {__version__}")
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser(
        "init", help="Scaffold a workspace (charter.yaml, queries/, .env.example)"
    )
    p_init.add_argument("directory", nargs="?", default=".")
    p_init.add_argument("--demo", action="store_true", help="Include a generated demo dataset")
    p_init.add_argument("--force", action="store_true", help="Overwrite an existing charter.yaml")
    p_init.add_argument(
        "--tour", action="store_true",
        help="With --demo: include guides, evals, a policy, and a seeded audit chain",
    )
    p_init.set_defaults(func=_cmd_init)

    p_serve = sub.add_parser("serve", help="Start the local server")
    p_serve.add_argument("directory", nargs="?", default=".")
    p_serve.add_argument(
        "--host", default="127.0.0.1", help="Bind address (default: localhost only)"
    )
    p_serve.add_argument("--port", type=int, default=8321)
    p_serve.add_argument(
        "--no-spill", action="store_true", help="Fail queries instead of spilling to disk"
    )
    p_serve.add_argument(
        "--local", action="store_true", help="Use a local Ollama model for the agent"
    )
    p_serve.add_argument("--model", help="Model name (with --local; default qwen3:8b)")
    p_serve.add_argument(
        "--offline",
        action="store_true",
        help="No-egress mode: disable the LLM agent and print a no-egress attestation",
    )
    p_serve.set_defaults(func=_cmd_serve)

    p_secrets = sub.add_parser("secrets", help="Manage ${NAME} secrets in the OS keyring")
    sec_sub = p_secrets.add_subparsers(dest="action")
    p_set = sec_sub.add_parser("set", help="Store a secret (prompts if --value omitted)")
    p_set.add_argument("name")
    p_set.add_argument("--value", help="Value (omit to be prompted without echo)")
    sec_sub.add_parser("rm", help="Remove a secret").add_argument("name")
    sec_sub.add_parser("list", help="List secret names stored via datacharter")
    p_secrets.set_defaults(func=_cmd_secrets)

    p_demo = sub.add_parser(
        "demo", help="Narrated governance walkthrough, out of the box (masking, read-only)"
    )
    p_demo.add_argument(
        "directory", nargs="?", default=None,
        help="Workspace to demo (default: scaffold a throwaway demo dataset)",
    )
    p_demo.set_defaults(func=_cmd_demo)

    from datacharter.agent.connect import CLIENTS

    p_connect = sub.add_parser(
        "connect", help="Print MCP-client config (+ deeplinks) to connect an agent to a workspace"
    )
    p_connect.add_argument("directory", nargs="?", default=".", help="Workspace (default: .)")
    p_connect.add_argument("--client", choices=[*CLIENTS, "all"], default="all")
    p_connect.add_argument(
        "--serve-url", default=None,
        help="Emit HTTP config for a running `datacharter serve` instead of the local stdio server",
    )
    p_connect.set_defaults(func=_cmd_connect)

    p_import = sub.add_parser("import", help="Generate a charter from another tool's metadata")
    import_sub = p_import.add_subparsers(dest="importer", required=True)
    p_dbt = import_sub.add_parser("dbt", help="Build a charter.yaml from a dbt manifest.json")
    p_dbt.add_argument("manifest", help="Path to target/manifest.json")
    p_dbt.add_argument("-o", "--out", default=None, help="Output path (default: ./charter.yaml)")
    p_dbt.add_argument("--force", action="store_true", help="Overwrite an existing charter.yaml")
    p_dbt.set_defaults(func=_cmd_import_dbt)
    p_odcs = import_sub.add_parser("odcs", help="Build a charter.yaml from an ODCS data contract")
    p_odcs.add_argument("contract", help="Path to an ODCS DataContract (YAML or JSON)")
    p_odcs.add_argument("-o", "--out", default=None, help="Output path (default: ./charter.yaml)")
    p_odcs.add_argument("--force", action="store_true", help="Overwrite an existing charter.yaml")
    p_odcs.set_defaults(func=_cmd_import_odcs)

    p_export = sub.add_parser("export", help="Export the charter to another contract format")
    export_sub = p_export.add_subparsers(dest="exporter", required=True)
    p_eodcs = export_sub.add_parser("odcs", help="Export charter.yaml as an ODCS data contract")
    p_eodcs.add_argument("directory", nargs="?", default=".")
    p_eodcs.add_argument("-o", "--out", default=None, help="Output path (default: stdout)")
    p_eodcs.set_defaults(func=_cmd_export_odcs)

    p_mcp = sub.add_parser(
        "mcp", help="Run an MCP server over stdio exposing the governed query tools"
    )
    p_mcp.add_argument("directory", nargs="?", default=".")
    p_mcp.add_argument(
        "--serve-url",
        default=None,
        help="Proxy tools to a running `datacharter serve` instead of opening a local engine",
    )
    p_mcp.set_defaults(func=_cmd_mcp)

    p_diff = sub.add_parser("diff", help="Diff two relations (rows only in each + common count)")
    p_diff.add_argument("left")
    p_diff.add_argument("right")
    p_diff.add_argument("directory", nargs="?", default=".")
    p_diff.add_argument("--key", help="Comma-separated key columns for changed-row detection")
    p_diff.set_defaults(func=_cmd_diff)

    p_scan = sub.add_parser("scan", help="Scan sources and suggest PII columns for charter.yaml")
    p_scan.add_argument("directory", nargs="?", default=".")
    p_scan.add_argument(
        "--write", action="store_true", help="Merge suggested PII into charter.yaml"
    )
    p_scan.add_argument(
        "--strict", action="store_true",
        help="Exit non-zero if literal PII is found in guides/context (for CI)",
    )
    p_scan.set_defaults(func=_cmd_scan)

    p_drift = sub.add_parser(
        "drift", help="Report schema drift: declared tables/PII + column shape vs a baseline"
    )
    p_drift.add_argument("directory", nargs="?", default=".")
    p_drift.add_argument(
        "--update", action="store_true", help="Record the current schema as the new baseline"
    )
    p_drift.set_defaults(func=_cmd_drift)

    p_access = sub.add_parser(
        "access", help="Review the agent-visible access surface (Access Plan)"
    )
    access_sub = p_access.add_subparsers(dest="access_action")
    p_access_diff = access_sub.add_parser(
        "diff",
        help="Diff the effective agent access surface between two charter versions",
    )
    p_access_diff.add_argument("directory", nargs="?", default=".")
    p_access_diff.add_argument(
        "--against", default="git:HEAD",
        help="Old side as a git ref (default: git:HEAD). Ignored when --old is given.",
    )
    p_access_diff.add_argument(
        "--old", help="Old charter file to compare against (overrides --against)"
    )
    p_access_diff.add_argument("--new", help="New charter file (default: WORKSPACE/charter.yaml)")
    p_access_diff.add_argument("--json", action="store_true", help="Emit the diff as JSON")
    p_access_diff.add_argument(
        "--md", action="store_true", help="Emit the diff as Markdown (for PR comments)"
    )
    p_access_diff.add_argument(
        "--fail-on", choices=["widened"], dest="fail_on",
        help="Exit 2 if any change widens the agent-visible surface (CI merge gate)",
    )
    p_access.set_defaults(func=_cmd_access, access_action=None)

    p_explain = sub.add_parser(
        "explain", help="Show a query's plan and row estimates without running it"
    )
    p_explain.add_argument("sql")
    p_explain.add_argument("directory", nargs="?", default=".")
    p_explain.set_defaults(func=_cmd_explain)

    p_sample = sub.add_parser(
        "sample", help="Print a PII-masked CSV sample of a relation (safe to share)"
    )
    p_sample.add_argument("relation")
    p_sample.add_argument("--rows", type=int, default=10, help="Rows to sample (default 10)")
    p_sample.add_argument("directory", nargs="?", default=".")
    p_sample.set_defaults(func=_cmd_sample)

    p_query = sub.add_parser("query", help="Run a read-only SQL query and print the result")
    p_query.add_argument("sql")
    p_query.add_argument("directory", nargs="?", default=".")
    p_query.add_argument(
        "--format", choices=["table", "csv", "json"], default="table", help="Output format"
    )
    p_query.set_defaults(func=_cmd_query)

    p_asof = sub.add_parser(
        "asof", help="Governance time-travel: the agent surface (or a masked query) as of a git ref"
    )
    p_asof.add_argument("ref", help="Git ref of the charter version (e.g. main~5 or a commit sha)")
    p_asof.add_argument("directory", nargs="?", default=".")
    p_asof.add_argument("--query", help="Run this SQL, masked by the ref charter's PII rules")
    p_asof.add_argument("--relation", help="Masked sample of a relation under the ref's rules")
    p_asof.add_argument("--rows", type=int, default=20, help="Row limit for --query/--relation")
    p_asof.add_argument("--json", action="store_true", help="Emit the surface snapshot as JSON")
    p_asof.set_defaults(func=_cmd_asof)

    p_monitor = sub.add_parser(
        "monitor", help="Continuous compliance: run every governance gate and report one status"
    )
    p_monitor.add_argument("directory", nargs="?", default=".")
    p_monitor.add_argument(
        "--json", action="store_true", help="Emit the report as JSON (for alerting)"
    )
    p_monitor.add_argument(
        "--no-gauntlet", action="store_true", dest="no_gauntlet",
        help="Skip the redteam gauntlet (faster; run the fast gates only)",
    )
    p_monitor.set_defaults(func=_cmd_monitor)

    p_dp = sub.add_parser(
        "dp", help="Differential-privacy query mode: Laplace-noise an aggregate under an ε budget"
    )
    p_dp.add_argument("sql", nargs="?", help="Aggregate SQL (COUNT/SUM/… or GROUP BY)")
    p_dp.add_argument("directory", nargs="?", default=".")
    p_dp.add_argument("--epsilon", type=float, default=1.0, help="Privacy loss for this query")
    p_dp.add_argument(
        "--bound", type=float,
        help="Value bound for a SUM (its sensitivity). Omit for COUNT (sensitivity 1).",
    )
    p_dp.add_argument("--budget", type=float, default=5.0, help="Total ε cap for the workspace")
    p_dp.add_argument("--status", action="store_true", help="Show budget spent/remaining and exit")
    p_dp.add_argument("--reset", action="store_true", help="Reset the spent budget and exit")
    p_dp.set_defaults(func=_cmd_dp)

    p_metric = sub.add_parser(
        "metric", help="Run a contract-defined metric (charter.yaml metrics:)"
    )
    p_metric.add_argument("name")
    p_metric.add_argument("--by", help="Comma-separated dimensions to group by")
    p_metric.add_argument(
        "--grain",
        choices=["day", "week", "month", "quarter", "year"],
        help="Time grain to group by (needs a metric time_column)",
    )
    p_metric.add_argument("directory", nargs="?", default=".")
    p_metric.set_defaults(func=_cmd_metric)

    p_test = sub.add_parser(
        "test", help="Run charter data assertions (exits non-zero if any fail)"
    )
    p_test.add_argument("directory", nargs="?", default=".")
    p_test.add_argument("--select", help="Run only the named test")
    p_test.set_defaults(func=_cmd_test)

    p_audit = sub.add_parser(
        "audit",
        help="Show, verify, or export the agent data-access audit log",
        description="Usage: datacharter audit [WORKSPACE] [verify|export]",
    )
    p_audit.add_argument(
        "tokens", nargs="*",
        help="Optional workspace path and/or action (verify, export) in either order",
    )
    p_audit.add_argument("--since", help="ISO timestamp lower bound (export)")
    p_audit.add_argument("--until", help="ISO timestamp upper bound (export)")
    p_audit.add_argument("--out", help="Output zip path (export)")
    p_audit.set_defaults(func=_cmd_audit)

    p_suggest = sub.add_parser(
        "suggest",
        help="Mine query history for guide suggestions (self-writing guides)",
    )
    p_suggest.add_argument("directory", nargs="?", default=".")
    p_suggest.add_argument(
        "--apply", action="store_true", help="Append suggestions to guides/suggested.md"
    )
    p_suggest.set_defaults(func=_cmd_suggest)

    p_canary = sub.add_parser(
        "canary",
        help="Canary tripwire status, or `drill` to test the alarm path",
        description="Usage: datacharter canary [WORKSPACE] [status|drill]",
    )
    p_canary.add_argument(
        "tokens", nargs="*",
        help="Optional workspace path and/or action (status, drill) in either order",
    )
    p_canary.set_defaults(func=_cmd_canary)

    p_redteam = sub.add_parser(
        "redteam",
        help="The Gauntlet: attack this charter's own governance and score it",
        description=(
            "Fire a static, offline battery of attacks (PII exfil, read-only "
            "bypass, policy evasion, honeytoken theft) through the real governed "
            "tool path. Exits 1 on any breach — a CI gate proving governance holds."
        ),
    )
    p_redteam.add_argument("directory", nargs="?", default=".")
    p_redteam.set_defaults(func=_cmd_redteam)

    p_eval = sub.add_parser(
        "eval", help="Run agent eval suites (evals/*.yaml) and score answers"
    )
    p_eval.add_argument("directory", nargs="?", default=".")
    p_eval.add_argument("--suite", help="Run only this suite (filename stem)")
    p_eval.add_argument(
        "--compare-guides", action="store_true",
        help="Run with and without guides and report the lift",
    )
    p_eval.add_argument(
        "--judge", action="store_true", help="Also score freeform answers with an LLM judge"
    )
    p_eval.add_argument("--samples", type=int, default=1, help="Runs per case; pass = majority")
    p_eval.add_argument(
        "--threshold", type=float, help="Exit nonzero if the pass rate is below this (0..1)"
    )
    p_eval.add_argument("--local", action="store_true", help="Use a local Ollama model")
    p_eval.add_argument("--model", help="Model id (overrides DATACHARTER_MODEL)")
    p_eval.add_argument(
        "--history", action="store_true", help="Show the eval-run trend for this workspace"
    )
    p_eval.set_defaults(func=_cmd_eval)

    p_lineage = sub.add_parser(
        "lineage", help="Show cross-source lineage aggregated from query history"
    )
    p_lineage.add_argument("directory", nargs="?", default=".")
    p_lineage.add_argument("--relation", help="Filter to one relation")
    p_lineage.add_argument("--json", action="store_true", help="Emit the graph as JSON")
    p_lineage.set_defaults(func=_cmd_lineage)

    p_ol = sub.add_parser(
        "openlineage",
        help="Emit the governed catalog as an OpenLineage event (Marquez/DataHub/OpenMetadata)",
    )
    p_ol.add_argument("directory", nargs="?", default=".")
    p_ol.add_argument("--url", help="OpenLineage receiver base URL (posts to <url>/api/v1/lineage)")
    p_ol.add_argument("--namespace", default="datacharter", help="OpenLineage namespace")
    p_ol.add_argument("--job", help="Job name (default govern.<workspace>)")
    p_ol.add_argument("-o", "--out", help="Write the event JSON to a file instead of posting")
    p_ol.set_defaults(func=_cmd_openlineage)

    p_prov = sub.add_parser(
        "provenance",
        help="Signed, independently-verifiable answer-provenance receipts",
    )
    prov_sub = p_prov.add_subparsers(dest="prov_action")
    p_kg = prov_sub.add_parser("keygen", help="Create the workspace signing key")
    p_kg.add_argument("directory", nargs="?", default=".")
    p_kg.add_argument("--force", action="store_true", help="Replace an existing key")
    p_pk = prov_sub.add_parser("pubkey", help="Print the public key (publish it for verifiers)")
    p_pk.add_argument("directory", nargs="?", default=".")
    p_seal = prov_sub.add_parser(
        "seal", help="Run a query through the governed surface and emit a signed receipt"
    )
    p_seal.add_argument("sql")
    p_seal.add_argument("directory", nargs="?", default=".")
    p_seal.add_argument("-o", "--out", help="Write the receipt JSON to a file (default stdout)")
    p_seal.add_argument("--model", help="Record the model that produced the answer")
    p_verify = prov_sub.add_parser("verify", help="Verify a receipt offline")
    p_verify.add_argument("receipt")
    p_verify.add_argument("--pubkey", help="Pin the expected public key (hex) you trust")
    p_verify.add_argument("--flight", help="Workspace dir — also check the audit-chain link")
    p_prov.set_defaults(func=_cmd_provenance, prov_action=None)

    p_snap = sub.add_parser("snapshot", help="Save a query result as local.<name> plus its SQL")
    p_snap.add_argument("name")
    p_snap.add_argument("sql")
    p_snap.add_argument("directory", nargs="?", default=".")
    p_snap.set_defaults(func=_cmd_snapshot)

    p_recheck = sub.add_parser(
        "recheck", help="Re-run a snapshot's query and diff vs the saved result"
    )
    p_recheck.add_argument("name")
    p_recheck.add_argument("directory", nargs="?", default=".")
    p_recheck.set_defaults(func=_cmd_recheck)

    args = parser.parse_args(argv)
    if args.command == "secrets" and not getattr(args, "action", None):
        p_secrets.print_help()
        return 1
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    try:
        return args.func(args)
    except Exception as exc:  # noqa: BLE001 — narrowed below; lazy imports keep startup fast
        from datacharter.contracts import CharterError
        from datacharter.engine.session import EngineError

        if isinstance(exc, (CharterError, EngineError)):
            # Anything that escapes a subcommand's own handling still prints as
            # a clean, actionable message — never a traceback.
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        raise


if __name__ == "__main__":
    sys.exit(main())
