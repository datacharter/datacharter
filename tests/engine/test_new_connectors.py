"""Excel and DuckDB-file source types: registration SQL and end-to-end queries."""

import duckdb

from datacharter.engine.session import Engine
from datacharter.engine.sources import qualified_name, registration_sql
from datacharter.models import ATTACH_TYPES, FILE_TYPES, Source, SourceType


def test_duckdb_and_excel_in_type_sets():
    assert SourceType.DUCKDB in ATTACH_TYPES
    assert SourceType.EXCEL in FILE_TYPES


def test_duckdb_file_registration(tmp_path):
    s = Source(name="db", type=SourceType.DUCKDB, path="x.duckdb")
    stmts = registration_sql(s, tmp_path)
    assert stmts == [f"ATTACH '{(tmp_path / 'x.duckdb').resolve()}' AS db (READ_ONLY)"]
    assert qualified_name(s, "t") == "db.main.t"


def test_excel_registration(tmp_path):
    s = Source(name="xl", type=SourceType.EXCEL, path="b.xlsx")
    sql = registration_sql(s, tmp_path)[-1]
    assert "read_xlsx(" in sql and "CREATE OR REPLACE VIEW xl" in sql


def test_duckdb_file_end_to_end(tmp_path):
    dbfile = tmp_path / "store.duckdb"
    con = duckdb.connect(str(dbfile))
    con.execute("CREATE TABLE widgets AS SELECT * FROM (VALUES (1, 'a'), (2, 'b')) t(id, name)")
    con.close()
    src = Source(name="store", type=SourceType.DUCKDB, path="store.duckdb", tables=["widgets"])
    with Engine(tmp_path, [src]) as eng:
        out = eng.query_sync("SELECT count(*) AS n FROM store__widgets")
        assert out.rows[0][0] == 2


def test_excel_end_to_end(tmp_path):
    xlsx = tmp_path / "book.xlsx"
    con = duckdb.connect()
    con.execute("INSTALL excel; LOAD excel")
    con.execute(
        "COPY (SELECT * FROM (VALUES (1, 'x'), (2, 'y'), (3, 'z')) t(id, label)) "
        f"TO '{xlsx}' WITH (FORMAT xlsx, HEADER true)"
    )
    con.close()
    src = Source(name="wb", type=SourceType.EXCEL, path="book.xlsx")
    with Engine(tmp_path, [src]) as eng:
        out = eng.query_sync("SELECT count(*) AS n FROM wb")
        assert out.rows[0][0] == 3
