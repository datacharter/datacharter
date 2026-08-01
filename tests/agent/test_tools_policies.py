"""Policies enforced end-to-end at the agent chokepoint."""

import asyncio
import json

import pytest

from datacharter.agent.tools import ToolBox
from datacharter.audit.evidence import read_entries
from datacharter.audit.recorder import FlightRecorder
from datacharter.cli import main as cli_main
from datacharter.contracts import load_charter
from datacharter.contracts.policies import parse_policies
from datacharter.engine.session import Engine


@pytest.fixture
def policed(tmp_path):
    cli_main(["init", str(tmp_path), "--demo"])
    charter = load_charter(tmp_path)
    policies = parse_policies({
        "store.customers": ["aggregates only", "groups of at least 5", "no joins to orders"],
    })
    eng = Engine(tmp_path, charter.sources).start()
    try:
        yield tmp_path, eng, charter, policies
    finally:
        eng.close()


def _run(box, sql):
    return asyncio.run(box.run("query", json.dumps({"sql": sql})))


def test_raw_select_refused_and_recorded(policed):
    ws, eng, charter, policies = policed
    rec = FlightRecorder(ws)
    rec.start_session("chat")
    box = ToolBox(eng, charter.sources, recorder=rec, policies=policies)
    out = _run(box, "SELECT email FROM store.customers")
    assert out.startswith("Error: policy —") and "aggregates only" in out
    access = [e for e in read_entries(ws) if e["type"] == "access"]
    assert access[-1]["error"].startswith("Error: policy")


def test_aggregate_allowed_small_groups_suppressed(policed):
    ws, eng, charter, policies = policed
    box = ToolBox(eng, charter.sources, policies=policies)
    out = json.loads(_run(box, (
        "SELECT tier, count(*) AS n FROM store.customers GROUP BY tier"
    )))
    assert "rows" in out
    assert all(row[1] >= 5 for row in out["rows"])  # every surviving group ≥ k
    assert any("k-anonymity" in w for w in out.get("warnings", []))


def test_join_restriction(policed):
    ws, eng, charter, policies = policed
    box = ToolBox(eng, charter.sources, policies=policies)
    out = _run(box, (
        "SELECT count(*) FROM store.customers c JOIN store.orders o "
        "ON c.id = o.customer_id"
    ))
    assert out.startswith("Error: policy —") and "queried together" in out


def test_unpolicied_tables_unaffected(policed):
    ws, eng, charter, policies = policed
    box = ToolBox(eng, charter.sources, policies=policies)
    out = json.loads(_run(box, "SELECT * FROM store.orders LIMIT 3"))
    assert out["row_count"] == 3


def test_describe_table_shows_policies(policed):
    ws, eng, charter, policies = policed
    box = ToolBox(eng, charter.sources, policies=policies)
    out = json.loads(asyncio.run(
        box.run("describe_table", json.dumps({"relation": "store.customers"}))
    ))
    assert "aggregates only" in out["policies"]
    assert "groups of at least 5" in out["policies"]
