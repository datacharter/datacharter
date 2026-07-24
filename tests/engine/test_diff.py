import pytest

from datacharter.cli import main as cli_main
from datacharter.contracts import load_charter
from datacharter.engine.session import Engine, EngineError


@pytest.fixture
def engine(tmp_path):
    cli_main(["init", str(tmp_path), "--demo"])
    charter = load_charter(tmp_path)
    eng = Engine(tmp_path, charter.sources).start()
    try:
        yield eng
    finally:
        eng.close()


async def test_diff_counts_and_rows(engine):
    engine.query_sync(
        "CREATE TABLE local.a AS SELECT * FROM (VALUES (1,'x'),(2,'y'),(3,'z')) t(id,v)"
    )
    engine.query_sync(
        "CREATE TABLE local.b AS SELECT * FROM (VALUES (2,'y'),(3,'zz'),(4,'w')) t(id,v)"
    )
    result = await engine.diff("local.a", "local.b")
    assert result.columns == ["id", "v"]
    assert result.left_only_count == 2  # (1,x) and (3,z)
    assert result.right_only_count == 2  # (3,zz) and (4,w)
    assert result.common_count == 1  # (2,y)
    assert {tuple(r) for r in result.left_only} == {(1, "x"), (3, "z")}


async def test_diff_identical_relations_report_no_differences(engine):
    engine.query_sync("CREATE TABLE local.a AS SELECT 1 AS id")
    engine.query_sync("CREATE TABLE local.b AS SELECT 1 AS id")
    result = await engine.diff("local.a", "local.b")
    assert result.left_only_count == 0
    assert result.right_only_count == 0
    assert result.common_count == 1
    assert result.columns == ["id"]  # columns are reported even with no diff rows


async def test_diff_across_sources(engine):
    engine.query_sync("CREATE TABLE local.cust AS SELECT * FROM store.customers")
    result = await engine.diff("store.customers", "local.cust")  # file source vs local catalog
    assert result.left_only_count == 0
    assert result.right_only_count == 0
    assert result.common_count == 3


async def test_diff_rejects_unsafe_relation(engine):
    with pytest.raises(EngineError):
        await engine.diff("a; DROP TABLE x", "local.b")


async def test_diff_by_key_detects_changed(engine):
    engine.query_sync(
        "CREATE TABLE local.a AS SELECT * FROM (VALUES (1,'x'),(2,'y'),(3,'z')) t(id,v)"
    )
    engine.query_sync(
        "CREATE TABLE local.b AS SELECT * FROM (VALUES (2,'y'),(3,'ZZ'),(4,'w')) t(id,v)"
    )
    result = await engine.diff("local.a", "local.b", key=["id"])
    assert result.left_only_count == 1  # id=1 removed
    assert result.right_only_count == 1  # id=4 added
    assert result.common_count == 2  # ids 2 and 3 matched by key
    assert result.changed_count == 1  # id=3 changed (z -> ZZ)


async def test_diff_by_key_rejects_bad_key(engine):
    engine.query_sync("CREATE TABLE local.a AS SELECT 1 AS id")
    with pytest.raises(EngineError):
        await engine.diff("local.a", "local.a", key=["id; DROP"])
