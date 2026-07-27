"""ToolBox masks agent-facing query VALUES per effective agent-access; schema stays visible."""

import json

from datacharter.agent.tools import ToolBox
from datacharter.cli import main as core_main
from datacharter.contracts import load_charter
from datacharter.engine.session import Engine


def _tb(tmp_path, sources, auto_pii=None):
    eng = Engine(tmp_path, sources).start()
    return eng, ToolBox(eng, sources, auto_pii=auto_pii or set())


def _q(tb, sql):
    import asyncio

    return json.loads(asyncio.run(tb.run("query", json.dumps({"sql": sql}))))


def test_pii_masked_by_default_in_query(tmp_path):
    core_main(["init", str(tmp_path), "--demo"])  # store.customers.email is declared PII
    charter = load_charter(tmp_path)
    eng, tb = _tb(tmp_path, charter.sources)
    try:
        out = _q(tb, "SELECT email FROM store.customers LIMIT 1")
        assert out["rows"][0][0] == "•••"
    finally:
        eng.close()


def test_field_override_on_unmasks(tmp_path):
    core_main(["init", str(tmp_path), "--demo"])
    charter = load_charter(tmp_path)
    for s in charter.sources:
        if s.name == "store":
            s.agent_access = {"columns": {"customers.email": True}}  # on = real
    eng, tb = _tb(tmp_path, charter.sources)
    try:
        out = _q(tb, "SELECT email FROM store.customers LIMIT 1")
        assert out["rows"][0][0] != "•••" and "@" in out["rows"][0][0]
    finally:
        eng.close()


def test_non_pii_override_off_masks(tmp_path):
    core_main(["init", str(tmp_path), "--demo"])
    charter = load_charter(tmp_path)
    for s in charter.sources:
        if s.name == "store":
            s.agent_access = {"columns": {"customers.tier": False}}  # off = masked
    eng, tb = _tb(tmp_path, charter.sources)
    try:
        out = _q(tb, "SELECT tier FROM store.customers LIMIT 1")
        assert out["rows"][0][0] == "•••"
    finally:
        eng.close()


def test_select_star_honors_override_without_lineage(tmp_path):
    # SELECT * often has no per-column lineage; the override must still apply via the
    # touched relation (regression: a masked non-PII column leaked through SELECT *).
    core_main(["init", str(tmp_path), "--demo"])
    charter = load_charter(tmp_path)
    for s in charter.sources:
        if s.name == "store":
            s.agent_access = {"columns": {"customers.id": False}}  # mask non-PII id
    eng, tb = _tb(tmp_path, charter.sources)
    try:
        out = _q(tb, "SELECT * FROM store.customers LIMIT 1")
        colmap = dict(zip(out["columns"], out["rows"][0], strict=True))
        assert colmap["id"] == "•••"  # override applied even without lineage
        assert colmap["email"] == "•••"  # PII default still masked
        assert colmap["tier"] != "•••"  # untouched -> real
    finally:
        eng.close()


def test_describe_shows_schema_unmasked(tmp_path):
    core_main(["init", str(tmp_path), "--demo"])
    charter = load_charter(tmp_path)
    eng, tb = _tb(tmp_path, charter.sources)
    try:
        import asyncio

        args = json.dumps({"relation": "store.customers"})
        out = json.loads(asyncio.run(tb.run("describe_table", args)))
        flat = json.dumps(out)
        assert "email" in flat and "•••" not in flat  # column name visible, no value masking
    finally:
        eng.close()


def test_local_snapshot_access_toggle(tmp_path):
    """A snapshot's PII column is masked by default; a local_access override flips it."""
    core_main(["init", str(tmp_path), "--demo"])
    sources = load_charter(tmp_path).sources
    eng = Engine(tmp_path, sources).start()
    try:
        eng.snapshot_sync("SELECT email FROM store.customers", "snap")
        default = _q(ToolBox(eng, sources), "SELECT email FROM local.snap")
        assert default["masked_columns"] == ["email"]  # name-based default protects it
        assert all(row[0] == "•••" for row in default["rows"])
        overridden = _q(
            ToolBox(eng, sources, local_access={"columns": {"snap.email": True}}),
            "SELECT email FROM local.snap",
        )
        assert "masked_columns" not in overridden  # toggled ON -> nothing masked
        assert all(row[0] != "•••" for row in overridden["rows"])  # real values
    finally:
        eng.close()
