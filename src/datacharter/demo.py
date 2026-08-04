"""The demo dataset: a small sqlite `store` (customers + orders) for onboarding."""

from __future__ import annotations

import sqlite3
from pathlib import Path

# Descriptor for registering the demo as a real, deletable source (see POST /api/demo).
DEMO_SOURCE = {
    "name": "store",
    "type": "sqlite",
    "path": "demo/store.db",
    "tables": ["customers", "orders"],
    "pii": {"customers": ["email"]},
}

# The full tour workspace contract: policies + canaries + context on top of the
# demo source. Written by `init --demo --tour`, the ephemeral demo, and the
# launchpad's "Load the demo dataset" (pristine workspaces only).
TOUR_CHARTER = """\
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
    context:
      customers: "One row per customer. tier is their plan; email is PII."

# Plain-english policy: agents may only aggregate customers, and any group
# smaller than 2 is suppressed. Your own SQL in the editor is unaffected.
policies:
  store.customers:
    - aggregates only
    - groups of at least 2

# Tripwires: synthetic honeytokens that alarm if masking ever fails.
canary: on

# A governed metric. Try: datacharter metric revenue --grain month
metrics:
  revenue:
    relation: store.orders
    expression: round(sum(total), 2)
    dimensions: [customer_id]
    time_column: placed_on
"""

SEED_QUESTION = "What do the tiers look like?"
SEED_QUERIES = (
    "SELECT tier, count(*) AS n FROM store.customers GROUP BY tier",
    "SELECT email FROM store.customers",  # refused: policy is aggregates-only
)


def write_demo_data(workspace: Path, seed_tour: bool = False) -> None:
    """Write the demo `store.db` (customers + orders) under `<workspace>/demo/`."""
    demo = workspace / "demo"
    demo.mkdir(exist_ok=True)
    con = sqlite3.connect(str(demo / "store.db"))
    try:
        # Idempotent: a prior demo may have been loaded then deleted, leaving store.db.
        con.execute("DROP TABLE IF EXISTS customers")
        con.execute("DROP TABLE IF EXISTS orders")
        con.execute("CREATE TABLE customers (id INTEGER, email TEXT, tier TEXT)")
        con.executemany(
            "INSERT INTO customers VALUES (?, ?, ?)",
            [
                (1, "ada@example.com", "pro"),
                (2, "grace@example.com", "free"),
                (3, "edsger@example.com", "pro"),
            ],
        )
        con.execute("CREATE TABLE orders (customer_id INTEGER, total REAL, placed_on TEXT)")
        con.executemany(
            "INSERT INTO orders VALUES (?, ?, ?)",
            [
                ((i % 3) + 1, round((i * 37 % 200) + i * 0.5, 2), f"2026-01-{(i % 28) + 1:02d}")
                for i in range(90)
            ],
        )
        con.commit()
    finally:
        con.close()
    if seed_tour:
        seed_governance(workspace)


DEMO_GUIDE = """\
# How to read this data

- **Revenue** means `sum(total)` on `store.orders`. There are no refunds in this
  dataset, so gross and net are the same here.
- `store.customers.tier` is the plan a customer is on (`pro` or `free`).
- Customer `email` is PII: agents see it masked as •••, and the charter only
  lets agents *aggregate* this table — never list individuals.
"""

DEMO_EVALS = """\
# An eval suite: questions you actually ask, and what a correct answer must do.
# Run:  datacharter eval . --compare-guides
version: 1
cases:
  - question: "How many orders are there in total?"
    expect:
      - { type: sql_contains, value: "orders" }
      - { type: answer_matches, pattern: "90" }
  - question: "How many customers are on each tier?"
    expect:
      - { type: sql_contains, value: "customers" }
      - { type: sql_excludes, value: "email" }
"""


def merge_tour_governance(workspace: Path) -> None:
    """Add the tour's policies, canaries, and table context to an existing charter.

    Used by POST /api/demo after `create_source` has registered (and attached)
    the demo source — writing TOUR_CHARTER wholesale would skip the attach.
    """
    from ruamel.yaml import YAML

    path = workspace / "charter.yaml"
    yaml = YAML()
    data = yaml.load(path.read_text()) or {}
    data["policies"] = {"store.customers": ["aggregates only", "groups of at least 2"]}
    data["canary"] = "on"
    src = (data.get("sources") or {}).get("store")
    if isinstance(src, dict):
        src["context"] = {"customers": "One row per customer. tier is their plan; email is PII."}
    with path.open("w") as f:
        yaml.dump(data, f)


def seed_files(workspace: Path) -> None:
    """Write the demo guides, evals, and query history (no engine required)."""
    try:
        (workspace / "guides").mkdir(exist_ok=True)
        (workspace / "guides" / "analytics.md").write_text(DEMO_GUIDE)
        (workspace / "evals").mkdir(exist_ok=True)
        (workspace / "evals" / "demo.yaml").write_text(DEMO_EVALS)
    except OSError:
        return

    # Query history, so `datacharter suggest` has a real habit to mine.
    try:
        from datacharter.engine.history import record

        habit = (
            "SELECT tier, count(*) AS n FROM store.customers "
            "WHERE tier <> 'internal' GROUP BY tier"
        )
        provenance = {"relations": ["store.customers"], "columns": [], "lineage": {}}
        for _ in range(4):
            record(workspace, habit, 2, provenance)
    except Exception:
        pass


def seed_governance(workspace: Path) -> None:
    """Give the demo real guides, evals, query history, and a genuine audit chain.

    Everything here is produced by the real machinery — the audit entries are
    written by the flight recorder from actual tool calls, so the chain verifies.
    Seeding must never break `init`. Only for workspaces with NO running server
    (opens its own engine); a live server seeds through its own toolbox instead
    (POST /api/demo) — the state DB cannot be opened twice.
    """
    seed_files(workspace)

    # A real, hash-verifiable audit chain: one allowed aggregate, one refusal.
    try:
        import asyncio
        import json as _json

        from datacharter.agent.factory import build_toolbox, detect_auto_pii
        from datacharter.audit import FlightRecorder
        from datacharter.contracts import load_charter
        from datacharter.engine.session import Engine
        from datacharter.engine.statekey import resolve_state_key

        charter = load_charter(workspace)
        # Same key `serve` uses — otherwise the local state DB we create here
        # cannot be reopened later and the workspace fails to start.
        engine = Engine(workspace, charter.sources, local_key=resolve_state_key()).start()
        try:
            recorder = FlightRecorder(workspace)
            recorder.start_session("demo", model="demo-tour", question=SEED_QUESTION)
            box = build_toolbox(
                engine, charter, auto_pii=asyncio.run(detect_auto_pii(engine)),
                recorder=recorder,
            )
            for sql in SEED_QUERIES:
                asyncio.run(box.run("query", _json.dumps({"sql": sql})))
        finally:
            engine.close()
    except Exception:
        pass
