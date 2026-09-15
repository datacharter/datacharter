"""GovernedToolBox prunes catalog and refuses unauthorized SQL."""

import json

from datacharter.agent.tools import ToolBox
from datacharter.cli import main as cli_main
from datacharter.contracts import load_charter
from datacharter.contracts.grants import CharterPolicy, PrincipalRef
from datacharter.engine.session import Engine
from datacharter.mcp.auth import Principal
from datacharter.mcp.governed import GovernedToolBox


def _box(tmp_path):
    assert cli_main(["init", str(tmp_path), "--demo"]) == 0
    charter = load_charter(tmp_path)
    eng = Engine(tmp_path, charter.sources).start()
    inner = ToolBox(eng, charter.sources)
    policy = CharterPolicy(
        principals={"analyst": PrincipalRef(sub="alice@corp")},
        grants={"analyst": ["store.orders"]},
    )
    box = GovernedToolBox(inner, Principal(subject="alice@corp"), policy)
    return eng, box


async def test_list_tables_omits_unpermitted(tmp_path):
    eng, box = _box(tmp_path)
    try:
        rows = json.loads(await box.run("list_tables", "{}"))
        rels = {r["relation"] for r in rows}
        assert "store.orders" in rels
        assert "store.customers" not in rels
    finally:
        eng.close()


async def test_describe_unpermitted_table_is_error(tmp_path):
    eng, box = _box(tmp_path)
    try:
        out = await box.run("describe_table", json.dumps({"relation": "store.customers"}))
        assert out.startswith("Error:")
        ok = await box.run("describe_table", json.dumps({"relation": "store.orders"}))
        assert not ok.startswith("Error:")
    finally:
        eng.close()


async def test_query_unpermitted_is_error_permitted_runs(tmp_path):
    eng, box = _box(tmp_path)
    try:
        denied = await box.run(
            "query", json.dumps({"sql": "SELECT count(*) FROM store.customers"})
        )
        assert denied.startswith("Error:")
        assert "not authorized" in denied.lower()
        allowed = await box.run(
            "query", json.dumps({"sql": "SELECT count(*) AS n FROM store.orders"})
        )
        assert not allowed.startswith("Error:")
        payload = json.loads(allowed)
        assert payload["rows"][0][0] == 90
    finally:
        eng.close()


async def test_unauthorized_query_is_recorded(tmp_path):
    from datacharter.audit.recorder import FLIGHT_DIR, FlightRecorder

    assert cli_main(["init", str(tmp_path), "--demo"]) == 0
    charter = load_charter(tmp_path)
    eng = Engine(tmp_path, charter.sources).start()
    rec = FlightRecorder(tmp_path, sink=None)
    inner = ToolBox(eng, charter.sources, recorder=rec)
    policy = CharterPolicy(
        principals={"analyst": PrincipalRef(sub="alice@corp")},
        grants={"analyst": ["store.orders"]},
    )
    box = GovernedToolBox(inner, Principal(subject="alice@corp"), policy)
    try:
        denied = await box.run(
            "query", json.dumps({"sql": "SELECT count(*) FROM store.customers"})
        )
        assert "not authorized" in denied.lower()
        accesses = []
        for seg in (tmp_path / FLIGHT_DIR).glob("[0-9]*.jsonl"):
            for line in seg.read_text().splitlines():
                if line.strip():
                    e = json.loads(line)
                    if e.get("type") == "access":
                        accesses.append(e)
        assert accesses
        assert any("not authorized" in (e.get("error") or "") for e in accesses)
    finally:
        eng.close()
