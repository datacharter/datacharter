"""Certified metrics as governed agent tools (list_metrics / query_metric).

query_metric resolves a charter `metrics:` entry to one SELECT and runs it
through the SAME query chokepoint — so it inherits the read-only guard, PII
masking, row filters, policies, canary scan, and audit for free.
"""

import asyncio
import json

import pytest

from datacharter.agent.factory import build_toolbox
from datacharter.agent.tools import ToolBox
from datacharter.audit.evidence import read_entries
from datacharter.audit.recorder import FlightRecorder
from datacharter.cli import main as cli_main
from datacharter.contracts import load_charter
from datacharter.engine.session import Engine


@pytest.fixture
def toured(tmp_path):
    """Demo workspace: store.customers/orders + a certified `revenue` metric."""
    cli_main(["init", str(tmp_path), "--demo"])
    charter = load_charter(tmp_path)
    eng = Engine(tmp_path, charter.sources).start()
    try:
        yield tmp_path, eng, charter
    finally:
        eng.close()


def _run(box, name, args):
    return asyncio.run(box.run(name, json.dumps(args)))


def _box(eng, charter, **kw):
    return build_toolbox(eng, charter, auto_pii=set(), **kw)


def test_list_metrics_reports_declared_metrics(toured):
    _ws, eng, charter = toured
    rows = json.loads(_run(_box(eng, charter), "list_metrics", {}))
    by_name = {r["name"]: r for r in rows}
    assert "revenue" in by_name
    rev = by_name["revenue"]
    assert rev["relation"] == "store.orders"
    assert "sum(total)" in rev["computes"]
    assert rev["has_time"] is True
    assert "customer_id" in rev["dimensions"]


def test_list_metrics_message_when_none_declared(tmp_path):
    cli_main(["init", str(tmp_path)])  # bare template — no metrics declared
    (tmp_path / "data.csv").write_text("a,b\n1,2\n")
    (tmp_path / "charter.yaml").write_text(
        "version: 1\nsources:\n  d:\n    type: csv\n    path: data.csv\n"
    )
    charter = load_charter(tmp_path)
    eng = Engine(tmp_path, charter.sources).start()
    try:
        out = _run(_box(eng, charter), "list_metrics", {})
    finally:
        eng.close()
    assert "No certified metrics" in out


def test_query_metric_runs_and_echoes_sql(toured):
    _ws, eng, charter = toured
    out = _run(_box(eng, charter), "query_metric", {"name": "revenue"})
    assert out.startswith("metric revenue — SQL: ")
    payload = json.loads(out.split("\n", 1)[1])
    assert payload["rows"] and payload["rows"][0][0] is not None


def test_query_metric_group_by_dimension(toured):
    _ws, eng, charter = toured
    out = _run(_box(eng, charter), "query_metric", {"name": "revenue", "by": ["customer_id"]})
    payload = json.loads(out.split("\n", 1)[1])
    assert "customer_id" in payload["columns"]
    assert len(payload["rows"]) >= 1


def test_query_metric_time_grain(toured):
    _ws, eng, charter = toured
    out = _run(_box(eng, charter), "query_metric", {"name": "revenue", "grain": "month"})
    assert "date_trunc" in out.lower() or "month" in out.lower()
    payload = json.loads(out.split("\n", 1)[1])
    assert payload["rows"]


def test_query_metric_unknown_name_lists_available(toured):
    _ws, eng, charter = toured
    out = _run(_box(eng, charter), "query_metric", {"name": "nope"})
    assert out.startswith("Error: unknown metric 'nope'")
    assert "revenue" in out


def test_query_metric_bad_grain_is_metric_error(toured):
    _ws, eng, charter = toured
    out = _run(_box(eng, charter), "query_metric", {"name": "revenue", "grain": "fortnight"})
    assert out.startswith("Error:")


def test_query_metric_inherits_audit(toured):
    ws, eng, charter = toured
    rec = FlightRecorder(ws)
    rec.start_session("chat")
    box = _box(eng, charter, recorder=rec)
    _run(box, "query_metric", {"name": "revenue"})
    access = [e for e in read_entries(ws) if e["type"] == "access"]
    assert any(e["tool"] == "query_metric" for e in access)


def test_metrics_absent_when_not_passed(toured):
    """A ToolBox built without metrics still answers list_metrics safely."""
    _ws, eng, charter = toured
    box = ToolBox(eng, charter.sources)  # no metrics kwarg
    assert "No certified metrics" in _run(box, "list_metrics", {})
    assert _run(box, "query_metric", {"name": "revenue"}).startswith("Error: unknown metric")
