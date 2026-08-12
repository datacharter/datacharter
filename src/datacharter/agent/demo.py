"""`datacharter demo` — a zero-config, narrated walkthrough of the governance.

Scaffolds a demo workspace (or uses one you point it at) and shows what an AI
agent actually sees through the governed tools: **PII masked**, **writes
refused**, the **contract in control** — with the raw data shown alongside so the
difference is visible. No server, no config, no account. It ends by pointing you
at `serve` / `mcp` to keep exploring.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

_CUSTOMERS_SQL = "SELECT id, email, tier FROM store.customers ORDER BY id LIMIT 3"


def _fmt_rows(rows) -> str:
    return "  ".join("(" + ", ".join(str(c) for c in row) + ")" for row in rows)


async def narrate(box, engine) -> list[str]:
    """Run the governed tools and return the walkthrough lines."""
    out: list[str] = []

    def say(line: str = "") -> None:
        out.append(line)

    say("  DataCharter — your data, governed for AI agents")
    say()

    tables = json.loads(await box.run("list_tables", "{}"))
    names = ", ".join(t.get("relation", "") for t in tables)
    say("═══ the agent's view of your data ═══")
    say(f"  list_tables → {names}")
    say()

    # PII masking: the same query, two views — what the agent gets vs the raw rows.
    governed = json.loads(await box.run("query", json.dumps({"sql": _CUSTOMERS_SQL})))
    raw = engine.query_sync(_CUSTOMERS_SQL)
    say("═══ PII masking — the agent never sees the raw value ═══")
    say('  "SELECT id, email, tier FROM store.customers":')
    say(f"    agent sees →  {_fmt_rows(governed['rows'])}")
    say(f"    raw data   →  {_fmt_rows([list(r) for r in raw.rows[:3]])}")
    say(f"    masked columns: {', '.join(governed.get('masked_columns') or []) or '(none)'}")
    say()

    # Read-only: a write is refused, not silently ignored.
    dropped = await box.run("query", json.dumps({"sql": "DROP TABLE store.customers"}))
    say("═══ read-only — the agent cannot mutate your data ═══")
    say("  DROP TABLE store.customers →")
    say(f"    {dropped.splitlines()[0][:96]}")
    say()

    say("  Every answer above came through the same tools an AI agent uses — governed")
    say("  by your charter.yaml, enforced on every call.")
    return out


def _scaffold(directory: str | None) -> tuple[Path, bool]:
    """Return (workspace, scaffolded). Uses `directory` if it holds a charter,
    else scaffolds a fresh demo workspace in a temp dir."""
    if directory and (Path(directory) / "charter.yaml").exists():
        return Path(directory).resolve(), False
    from datacharter.cli import main as cli_main

    ws = Path(tempfile.mkdtemp(prefix="dc-demo-")) / "workspace"
    cli_main(["init", str(ws), "--demo"])
    return ws, True


def run(directory: str | None = None) -> int:
    """Scaffold (or use) a workspace, narrate the governance, print next steps."""
    from datacharter.agent.factory import build_toolbox, detect_auto_pii
    from datacharter.cli import _open_engine
    from datacharter.contracts import load_charter

    ws, scaffolded = _scaffold(directory)
    charter = load_charter(ws)
    engine = _open_engine(ws, charter.sources)
    try:
        box = build_toolbox(engine, charter, auto_pii=asyncio.run(detect_auto_pii(engine)))
        print()
        for line in asyncio.run(narrate(box, engine)):
            print(line)
    finally:
        engine.close()
    print()
    print(f"  Explore it live:      datacharter serve {ws}")
    print(f"  Point an agent at it: datacharter mcp {ws}")
    if scaffolded:
        print("  (demo workspace scaffolded above — a throwaway copy, safe to delete)")
    return 0
