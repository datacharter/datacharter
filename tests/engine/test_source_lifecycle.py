import sqlite3

import pytest

from datacharter.engine.session import Engine, EngineError
from datacharter.models import Source, SourceType


def _sqlite(tmp_path):
    db = tmp_path / "crm.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE accounts (id INTEGER, org TEXT)")
    con.execute("INSERT INTO accounts VALUES (1, 'acme')")
    con.commit()
    con.close()
    return Source(name="crm", type=SourceType.SQLITE, path="crm.db", tables=["accounts"])


def test_remove_source_drops_views_and_detaches(tmp_path):
    with Engine(tmp_path, [_sqlite(tmp_path)]) as eng:
        assert eng.query_sync("SELECT org FROM crm__accounts").rows == [("acme",)]
        eng.remove_source("crm")
        assert all(s.name != "crm" for s in eng.sources)
        with pytest.raises(EngineError):
            eng.query_sync("SELECT org FROM crm__accounts")


def test_remove_source_is_idempotent(tmp_path):
    with Engine(tmp_path, [_sqlite(tmp_path)]) as eng:
        eng.remove_source("crm")
        eng.remove_source("crm")  # no raise


def test_test_source_ok_and_failure(tmp_path):
    good = _sqlite(tmp_path)
    # A DB source that can't be registered (no database) fails deterministically.
    bad = Source(
        name="bad",
        type=SourceType.POSTGRES,
        connection={"host": "x", "user": "u"},
        credentials={"password": "p"},
    )
    with Engine(tmp_path) as eng:
        eng.test_source(good)  # no raise
        with pytest.raises(EngineError):
            eng.test_source(bad)
