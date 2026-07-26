"""ToolBox applies row filters to the agent surface; masking composes; human path free."""

import asyncio
import json

from datacharter.agent.tools import ToolBox
from datacharter.contracts import load_charter
from datacharter.engine.session import Engine


def _ws(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "orders.csv").write_text(
        "id,email,region\n1,a@x.com,US\n2,b@x.com,EU\n3,c@x.com,US\n"
    )
    (tmp_path / "charter.yaml").write_text(
        "version: 1\nsources:\n  orders:\n    type: csv\n    path: data/orders.csv\n"
        "    pii:\n      orders:\n        - email\n"
        "    row_filters:\n      orders: \"region = 'US'\"\n"
    )
    charter = load_charter(tmp_path)
    eng = Engine(tmp_path, charter.sources).start()
    return eng, ToolBox(eng, charter.sources)


def _q(tb, sql):
    return json.loads(asyncio.run(tb.run("query", json.dumps({"sql": sql}))))


def test_agent_sees_only_filtered_rows(tmp_path):
    eng, tb = _ws(tmp_path)
    try:
        out = _q(tb, "SELECT id FROM orders ORDER BY id")
        assert [r[0] for r in out["rows"]] == [1, 3]  # EU row filtered out
    finally:
        eng.close()


def test_row_filter_and_column_mask_compose(tmp_path):
    eng, tb = _ws(tmp_path)
    try:
        out = _q(tb, "SELECT id, email FROM orders ORDER BY id")
        assert [r[0] for r in out["rows"]] == [1, 3]  # filtered
        assert all(r[1] == "•••" for r in out["rows"])  # email still masked
    finally:
        eng.close()


def test_human_query_is_unfiltered(tmp_path):
    eng, _ = _ws(tmp_path)
    try:
        res = eng.query_sync("SELECT count(*) AS n FROM orders")
        assert res.rows[0][0] == 3  # human sees all rows
    finally:
        eng.close()
