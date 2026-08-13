"""Pre-execution query-cost ceiling + agent-retryable denial messages."""

import asyncio
import json

import pytest

from datacharter.agent.factory import build_toolbox, detect_auto_pii
from datacharter.cli import _open_engine
from datacharter.contracts import load_charter
from datacharter.contracts.loader import CharterError


def _ws(tmp_path, *, ceiling=None, rows=100000, pii=False):
    (tmp_path / "big.csv").write_text(
        ("id,email\n" + "\n".join(f"{i},u{i}@x.com" for i in range(rows)) + "\n")
        if pii else
        ("id\n" + "\n".join(str(i) for i in range(rows)) + "\n")
    )
    charter = "version: 1\n"
    if ceiling is not None:
        charter += f"max_scan_rows: {ceiling}\n"
    charter += "sources:\n  big:\n    type: csv\n    path: big.csv\n"
    if pii:
        charter += "    pii:\n      big: [email]\n"
    (tmp_path / "charter.yaml").write_text(charter)
    return tmp_path


def _run(ws, sql):
    charter = load_charter(ws)
    engine = _open_engine(ws, charter.sources)
    try:
        box = build_toolbox(engine, charter, auto_pii=asyncio.run(detect_auto_pii(engine)))
        return asyncio.run(box.run("query", json.dumps({"sql": sql})))
    finally:
        engine.close()


def test_ceiling_blocks_unbounded_scan_with_retryable_message(tmp_path):
    out = _run(_ws(tmp_path, ceiling=50000), "SELECT id FROM big")
    assert out.startswith("Error:") and "ceiling" in out
    assert "To proceed" in out and ("WHERE" in out or "LIMIT" in out)


@pytest.mark.parametrize("sql", [
    "SELECT id FROM big LIMIT 1000",
    "SELECT id FROM big WHERE id = 5",
    "SELECT count(*) FROM big",
])
def test_ceiling_allows_narrowed_queries(tmp_path, sql):
    assert "row_count" in _run(_ws(tmp_path, ceiling=50000), sql)


def test_no_ceiling_by_default(tmp_path):
    assert "row_count" in _run(_ws(tmp_path), "SELECT id FROM big")  # no max_scan_rows


def test_charter_rejects_bad_ceiling(tmp_path):
    (tmp_path / "c.csv").write_text("a\n1\n")
    (tmp_path / "charter.yaml").write_text(
        "version: 1\nmax_scan_rows: -5\nsources:\n  c:\n    type: csv\n    path: c.csv\n"
    )
    with pytest.raises(CharterError, match="max_scan_rows"):
        load_charter(tmp_path)


def test_estimated_cost_reflects_limit(tmp_path):
    ws = _ws(tmp_path, rows=10000)
    charter = load_charter(ws)
    engine = _open_engine(ws, charter.sources)
    try:
        full = asyncio.run(engine.estimated_cost("SELECT id FROM big"))
        limited = asyncio.run(engine.estimated_cost("SELECT id FROM big LIMIT 5"))
    finally:
        engine.close()
    assert full is not None and full > 1000
    # LIMIT lowers the root estimate — to a small number or to none at all, either
    # of which passes a ceiling above it.
    assert limited is None or limited <= 5


def test_masked_column_denial_is_actionable(tmp_path):
    ws = _ws(tmp_path, rows=3, pii=True)
    out = _run(ws, "SELECT id FROM big WHERE email = 'u1@x.com'")
    assert "masked" in out and "To proceed" in out  # explains why + how to retry
