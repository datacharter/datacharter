"""DuckLake lakehouse source — metadata in a DuckDB/SQLite/Postgres/MySQL catalog,
data as Parquet on local/object storage, attached READ_ONLY via the `ducklake`
extension.

SQL-shape tests are deterministic. A local-file catalog needs no cloud, so the
end-to-end attach + governed query runs for real (gold-verified against the actual
ducklake extension), not skipped."""

import duckdb
import pytest

from datacharter.contracts import load_charter
from datacharter.engine.sources import SourceConfigError, qualified_name, registration_sql
from datacharter.models import ATTACH_TYPES, COMMUNITY_ATTACH_EXTENSIONS, Source, SourceType


def _src(**kw):
    kw.setdefault("name", "lake")
    kw.setdefault("type", SourceType.DUCKLAKE)
    return Source(**kw)


def test_ducklake_is_attach_type_installed_by_registration():
    assert SourceType.DUCKLAKE in ATTACH_TYPES
    # ducklake installs from the core repo inside its own registration, so it must
    # NOT be in the community-extension auto-install set.
    assert SourceType.DUCKLAKE not in COMMUNITY_ATTACH_EXTENSIONS


def test_local_file_catalog_registration(tmp_path):
    s = _src(connection={"metadata": "catalog.ducklake"})
    stmts = registration_sql(s, tmp_path)
    assert stmts[:2] == ["INSTALL ducklake", "LOAD ducklake"]
    # A bare path is resolved against the workspace and prefixed with the scheme.
    assert stmts[-1] == f"ATTACH 'ducklake:{tmp_path / 'catalog.ducklake'}' AS lake (READ_ONLY)"


def test_data_path_and_s3_secret(tmp_path):
    s = _src(
        connection={"metadata": "catalog.ducklake", "data_path": "s3://bucket/lake"},
        credentials={"key_id": "AK", "secret": "SK", "region": "us-east-1"},
    )
    stmts = registration_sql(s, tmp_path)
    assert any(x.startswith("CREATE OR REPLACE TEMPORARY SECRET lake_s3 (TYPE s3") for x in stmts)
    assert "SK" not in stmts[-1]  # secret stays out of the ATTACH string
    assert "DATA_PATH 's3://bucket/lake'" in stmts[-1] and stmts[-1].endswith("READ_ONLY)")


def test_sql_catalog_passthrough_installs_backend(tmp_path):
    s = _src(connection={"metadata": "postgres:dbname=meta host=db user=u"})
    stmts = registration_sql(s, tmp_path)
    assert "INSTALL postgres" in stmts and "LOAD postgres" in stmts
    # A scheme'd metadata is passed through verbatim (not resolved as a path).
    assert stmts[-1] == (
        "ATTACH 'ducklake:postgres:dbname=meta host=db user=u' AS lake (READ_ONLY)"
    )


def test_missing_metadata_errors(tmp_path):
    with pytest.raises(SourceConfigError, match="metadata"):
        registration_sql(_src(connection={}), tmp_path)


def test_qualified_name_defaults_to_main(tmp_path):
    assert qualified_name(_src(connection={"metadata": "c"}), "orders") == "lake.main.orders"
    s2 = _src(connection={"metadata": "c", "schema": "sales"})
    assert qualified_name(s2, "orders") == "lake.sales.orders"


def test_charter_interpolates_connection_env(tmp_path, monkeypatch):
    monkeypatch.setenv("LAKE_META", "prod.ducklake")
    (tmp_path / "charter.yaml").write_text(
        "version: 1\nsources:\n  lake:\n    type: ducklake\n"
        "    connection:\n      metadata: ${LAKE_META}\n    tables: [customers]\n"
    )
    charter = load_charter(tmp_path)
    # ${ENV} in a connection string now resolves (needed for a Postgres catalog DSN).
    assert charter.sources[0].connection["metadata"] == "prod.ducklake"


def _make_lake(tmp_path):
    """Create a real DuckLake catalog with a seeded table (local file + local data)."""
    meta = tmp_path / "catalog.ducklake"
    data = tmp_path / "lakedata"
    con = duckdb.connect()
    con.execute("INSTALL ducklake")
    con.execute("LOAD ducklake")
    con.execute(f"ATTACH 'ducklake:{meta}' AS lake (DATA_PATH '{data}')")
    con.execute(
        "CREATE TABLE lake.main.customers AS SELECT * FROM (VALUES "
        "(1,'ada@example.com','pro'),(2,'grace@example.com','free')) t(id,email,tier)"
    )
    con.execute("DETACH lake")
    con.close()
    return "catalog.ducklake"


def test_ducklake_end_to_end_governed_query(tmp_path):
    from datacharter.engine.session import Engine

    _make_lake(tmp_path)
    src = Source(name="lake", type=SourceType.DUCKLAKE,
                 connection={"metadata": "catalog.ducklake"}, tables=["customers"],
                 pii={"customers": ["email"]})
    with Engine(tmp_path, [src]) as eng:
        rows = eng.query_sync("SELECT id, tier FROM lake.main.customers ORDER BY id").rows
        assert rows == [(1, "pro"), (2, "free")]
        # The flat compatibility alias also resolves.
        assert eng.query_sync("SELECT count(*) FROM lake__customers").rows[0][0] == 2


def test_ducklake_masking_through_the_agent_surface(tmp_path):
    import asyncio

    from datacharter.agent.factory import build_toolbox, detect_auto_pii
    from datacharter.engine.session import Engine

    _make_lake(tmp_path)
    (tmp_path / "charter.yaml").write_text(
        "version: 1\nsources:\n  lake:\n    type: ducklake\n"
        "    connection:\n      metadata: catalog.ducklake\n"
        "    tables: [customers]\n    pii:\n      customers: [email]\n"
    )
    charter = load_charter(tmp_path)
    eng = Engine(tmp_path, charter.sources).start()
    try:
        import json
        tb = build_toolbox(eng, charter, auto_pii=asyncio.run(detect_auto_pii(eng)))
        out = asyncio.run(tb.run("query", json.dumps(
            {"sql": "SELECT id, email FROM lake.main.customers"})))
        assert "ada@example.com" not in out and "\\u2022" in out  # email masked
    finally:
        eng.close()
