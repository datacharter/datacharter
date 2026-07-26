"""ToolBox enforces a per-query statement timeout (the reliable half of the budget;
EXPLAIN can't give output cardinality, so no cardinality gate — the 50-row result
cap already bounds egress)."""

import asyncio
import json

from datacharter.agent.tools import ToolBox
from datacharter.cli import main as core_main
from datacharter.contracts import load_charter
from datacharter.engine.session import Engine


def _tb(tmp_path, **kw):
    core_main(["init", str(tmp_path), "--demo"])
    charter = load_charter(tmp_path)
    eng = Engine(tmp_path, charter.sources).start()
    return eng, ToolBox(eng, charter.sources, **kw)


def _run(tb, sql):
    return asyncio.run(tb.run("query", json.dumps({"sql": sql})))


def test_slow_query_hits_the_timeout(tmp_path):
    eng, tb = _tb(tmp_path, timeout_s=0.5)
    try:
        out = _run(tb, "SELECT count(*) FROM range(9000000000000)")
        assert out.startswith("Error:") and ("timeout" in out.lower() or "exceeded" in out.lower())
    finally:
        eng.close()


def test_normal_query_runs_within_budget(tmp_path):
    eng, tb = _tb(tmp_path)  # default 30s timeout
    try:
        out = json.loads(_run(tb, "SELECT count(*) AS n FROM store.customers"))
        assert out["rows"][0][0] == 3
    finally:
        eng.close()


def test_aggregate_over_large_scan_is_allowed(tmp_path):
    # A big scan that returns a tiny result must not be refused — only slow queries
    # (timeout) or big result sets (50-row cap) are bounded.
    eng, tb = _tb(tmp_path)
    try:
        eng.query_sync("CREATE TABLE local.big AS SELECT range AS x FROM range(2000000)")
        out = json.loads(_run(tb, "SELECT count(*) AS n FROM local.big"))
        assert out["rows"][0][0] == 2000000
    finally:
        eng.close()
