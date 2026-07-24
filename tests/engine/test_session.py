import sqlite3

import duckdb
import pytest

from datacharter.engine.guard import QueryNotAllowed
from datacharter.engine.session import Engine, EngineError, QueryTimeout
from datacharter.models import Source, SourceType


@pytest.fixture
def workspace(tmp_path):
    return tmp_path


def _csv_source(workspace, name="people"):
    path = workspace / "people.csv"
    path.write_text("id,name\n1,ada\n2,grace\n")
    return Source(name=name, type=SourceType.CSV, path="people.csv")


def _parquet_source(workspace, name="orders"):
    path = workspace / "orders.parquet"
    duckdb.sql(
        "COPY (SELECT * FROM (VALUES (1, 10.5), (2, 99.0)) t(person_id, total)) TO "
        f"'{path}' (FORMAT parquet)"
    )
    return Source(name=name, type=SourceType.PARQUET, path="orders.parquet")


def _sqlite_source(workspace, name="crm"):
    path = workspace / "crm.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE accounts (id INTEGER, org TEXT)")
    con.execute("INSERT INTO accounts VALUES (1, 'acme'), (2, 'initech')")
    con.commit()
    con.close()
    return Source(name=name, type=SourceType.SQLITE, path="crm.db")


def test_csv_view_query(workspace):
    with Engine(workspace, [_csv_source(workspace)]) as eng:
        result = eng.query_sync("SELECT name FROM people ORDER BY id")
        assert result.columns == ["name"]
        assert result.rows == [("ada",), ("grace",)]


def test_cross_source_join(workspace):
    sources = [_csv_source(workspace), _parquet_source(workspace), _sqlite_source(workspace)]
    with Engine(workspace, sources) as eng:
        result = eng.query_sync(
            """
            SELECT p.name, o.total, a.org
            FROM people p
            JOIN orders o ON o.person_id = p.id
            JOIN crm.accounts a ON a.id = p.id
            ORDER BY p.id
            """
        )
        assert result.rows == [("ada", 10.5, "acme"), ("grace", 99.0, "initech")]


def test_guard_enforced_via_engine(workspace):
    with Engine(workspace, [_csv_source(workspace)]) as eng, pytest.raises(QueryNotAllowed):
        eng.query_sync("DELETE FROM people")


def test_row_limit_truncation(workspace):
    with Engine(workspace) as eng:
        result = eng.query_sync("SELECT * FROM range(100)", row_limit=10)
        assert result.row_count == 10
        assert result.truncated is True


def test_local_persistence_roundtrip(workspace):
    key = "unit-test-key-123"
    with Engine(workspace, local_key=key) as eng:
        eng.query_sync("CREATE TABLE local.snap AS SELECT 42 AS answer")
    with Engine(workspace, local_key=key) as eng:
        result = eng.query_sync("SELECT answer FROM local.snap")
        assert result.rows == [(42,)]


def test_local_wrong_key_fails(workspace):
    with Engine(workspace, local_key="right-key-123"):
        pass
    with pytest.raises(EngineError):
        Engine(workspace, local_key="wrong-key-456").start()


def test_error_scrubs_credentials(workspace):
    src = Source(
        name="pg",
        type=SourceType.POSTGRES,
        connection={"host": "nowhere.invalid", "port": 5432, "database": "d", "user": "u"},
        credentials={"password": "supersecretpw"},
    )
    with pytest.raises(EngineError) as excinfo:
        Engine(workspace, [src]).start()
    assert "supersecretpw" not in str(excinfo.value)


def test_tmp_dir_wiped_on_close(workspace):
    eng = Engine(workspace).start()
    tmp = workspace / ".datacharter" / "tmp"
    assert tmp.exists()
    eng.close()
    assert not tmp.exists()


async def test_async_timeout_interrupts(workspace):
    with Engine(workspace) as eng:
        with pytest.raises(QueryTimeout):
            await eng.query(
                "SELECT count(*) FROM range(1000000000) a, range(1000) b",
                timeout_s=0.3,
            )
        # Session stays usable after an interrupt.
        result = eng.query_sync("SELECT 1")
        assert result.rows == [(1,)]
