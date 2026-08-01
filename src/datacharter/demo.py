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


def seed_governance(workspace: Path) -> None:
    """Give the demo real guides, evals, query history, and a genuine audit chain.

    Everything here is produced by the real machinery — the audit entries are
    written by the flight recorder from actual tool calls, so the chain verifies.
    Seeding must never break `init`.
    """
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
        for _ in range(4):
            record(workspace, habit, 2, {"relations": ["store.customers"], "columns": [], "lineage": {}})
    except Exception:
        pass

    # A real, hash-verifiable audit chain: one allowed aggregate, one refusal.
    try:
        import asyncio
        import json as _json

        from datacharter.agent.tools import ToolBox
        from datacharter.audit import FlightRecorder
        from datacharter.contracts import load_charter
        from datacharter.engine.session import Engine

        charter = load_charter(workspace)
        engine = Engine(workspace, charter.sources).start()
        try:
            recorder = FlightRecorder(workspace)
            recorder.start_session("demo", model="demo-tour", question="What do the tiers look like?")
            box = ToolBox(
                engine, charter.sources, guides=charter.guides,
                recorder=recorder, policies=charter.policies,
            )
            for sql in (
                "SELECT tier, count(*) AS n FROM store.customers GROUP BY tier",
                "SELECT email FROM store.customers",  # refused: policy is aggregates-only
            ):
                asyncio.run(box.run("query", _json.dumps({"sql": sql})))
        finally:
            engine.close()
    except Exception:
        pass
