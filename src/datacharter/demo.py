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


def write_demo_data(workspace: Path) -> None:
    """Write the demo `store.db` (customers + orders) under `<workspace>/demo/`."""
    demo = workspace / "demo"
    demo.mkdir(exist_ok=True)
    con = sqlite3.connect(str(demo / "store.db"))
    try:
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
