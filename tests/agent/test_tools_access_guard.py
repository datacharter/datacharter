"""ToolBox refuses agent queries that filter/join/group/order by a masked column."""

import asyncio
import json

from datacharter.agent.tools import ToolBox
from datacharter.cli import main as core_main
from datacharter.contracts import load_charter
from datacharter.engine.session import Engine


def _tb(tmp_path):
    core_main(["init", str(tmp_path), "--demo"])  # store.customers.email is declared PII
    charter = load_charter(tmp_path)
    eng = Engine(tmp_path, charter.sources).start()
    return eng, ToolBox(eng, charter.sources), charter


def _run(tb, sql):
    return asyncio.run(tb.run("query", json.dumps({"sql": sql})))


def test_where_on_masked_column_is_refused(tmp_path):
    eng, tb, _ = _tb(tmp_path)
    try:
        out = _run(tb, "SELECT id FROM store.customers WHERE email = 'ada@example.com'")
        assert out.startswith("Error:") and "masked" in out
    finally:
        eng.close()


def test_select_masked_column_still_works_and_is_masked(tmp_path):
    eng, tb, _ = _tb(tmp_path)
    try:
        out = json.loads(_run(tb, "SELECT email FROM store.customers LIMIT 1"))
        assert out["rows"][0][0] == "•••"
    finally:
        eng.close()


def test_where_on_non_pii_column_is_allowed(tmp_path):
    eng, tb, _ = _tb(tmp_path)
    try:
        out = json.loads(_run(tb, "SELECT id FROM store.customers WHERE tier = 'gold'"))
        assert "rows" in out
    finally:
        eng.close()


def test_toggled_on_pii_column_can_be_filtered(tmp_path):
    # override email access ON -> not masked -> filtering allowed
    core_main(["init", str(tmp_path), "--demo"])
    charter = load_charter(tmp_path)
    for s in charter.sources:
        if s.name == "store":
            s.agent_access = {"columns": {"customers.email": True}}
    eng = Engine(tmp_path, charter.sources).start()
    tb = ToolBox(eng, charter.sources)
    try:
        out = json.loads(_run(tb, "SELECT id FROM store.customers WHERE email LIKE '%@%'"))
        assert "rows" in out
    finally:
        eng.close()


def test_describe_table_lists_masked_columns(tmp_path):
    eng, tb, _ = _tb(tmp_path)
    try:
        out = json.loads(
            asyncio.run(tb.run("describe_table", json.dumps({"relation": "store.customers"})))
        )
        assert "email" in out.get("masked_columns", [])
        # names still visible in the schema body
        assert "email" in json.dumps(out)
    finally:
        eng.close()
