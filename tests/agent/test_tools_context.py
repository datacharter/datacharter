"""Table context + workspace guides reach the agent surface (describe_table, system prompt)."""

import asyncio
import json

from datacharter.agent.loop import SYSTEM_PROMPT, build_system
from datacharter.agent.tools import ToolBox
from datacharter.cli import main as core_main
from datacharter.contracts import load_charter
from datacharter.engine.session import Engine


def _describe(tb, relation):
    return json.loads(asyncio.run(tb.run("describe_table", json.dumps({"relation": relation}))))


def test_describe_table_includes_declared_context(tmp_path):
    core_main(["init", str(tmp_path), "--demo"])
    charter = load_charter(tmp_path)
    for s in charter.sources:
        if s.name == "store":
            s.table_context = {"customers": "Test accounts have tier = 'internal'; exclude them."}
    eng = Engine(tmp_path, charter.sources).start()
    try:
        tb = ToolBox(eng, charter.sources)
        out = _describe(tb, "store.customers")
        assert out["context"].startswith("Test accounts")
        # undeclared tables carry no context key
        assert "context" not in _describe(tb, "store.orders")
    finally:
        eng.close()


def test_context_parsed_from_charter_yaml(tmp_path):
    (tmp_path / "data.csv").write_text("id,region\n1,US\n")
    (tmp_path / "charter.yaml").write_text(
        "version: 1\n"
        "sources:\n"
        "  store:\n"
        "    type: csv\n"
        "    path: data.csv\n"
        "    context:\n"
        "      store: 'One row per order; region is ISO-ish.'\n"
    )
    charter = load_charter(tmp_path)
    assert charter.sources[0].table_context["store"].startswith("One row per order")
    eng = Engine(tmp_path, charter.sources).start()
    try:
        tb = ToolBox(eng, charter.sources)
        # single-file sources register as an unqualified relation; table-only match applies
        out = _describe(tb, "store")
        assert out["context"].startswith("One row per order")
    finally:
        eng.close()


def test_invalid_context_shape_rejected(tmp_path):
    import pytest

    from datacharter.contracts.loader import CharterError

    (tmp_path / "charter.yaml").write_text(
        "version: 1\nsources:\n  s:\n    type: csv\n    path: d.csv\n    context: nope\n"
    )
    with pytest.raises(CharterError, match="context"):
        load_charter(tmp_path)


def test_build_system_appends_guides():
    assert build_system("") == SYSTEM_PROMPT
    out = build_system("Revenue is net of refunds.")
    assert out.startswith(SYSTEM_PROMPT)
    assert "Workspace guides" in out
    assert "Revenue is net of refunds." in out


def test_toolbox_carries_guides(tmp_path):
    core_main(["init", str(tmp_path), "--demo"])
    charter = load_charter(tmp_path)
    eng = Engine(tmp_path, charter.sources).start()
    try:
        tb = ToolBox(eng, charter.sources, guides="Use store.orders for revenue.")
        assert tb.guides == "Use store.orders for revenue."
    finally:
        eng.close()
