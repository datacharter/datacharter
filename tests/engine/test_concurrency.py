"""Non-connector reads run concurrently; timeout stays per-query; spill pragma applies."""

import asyncio
import sqlite3
import time

import pytest

from datacharter.engine.session import Engine, QueryTimeout
from datacharter.models import Source, SourceType


def _engine(tmp_path):
    db = tmp_path / "crm.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE accounts (id INTEGER, org TEXT)")
    con.executemany("INSERT INTO accounts VALUES (?, ?)", [(1, "acme"), (2, "beta")])
    con.commit()
    con.close()
    src = Source(name="crm", type=SourceType.SQLITE, path="crm.db", tables=["accounts"])
    return Engine(tmp_path, [src]).start()


def test_concurrent_reads_do_not_serialize(tmp_path):
    eng = _engine(tmp_path)
    slow = "SELECT count(*) FROM range(1500000000) t(x) WHERE x % 7 = 3"
    try:

        async def main():
            t0 = time.perf_counter()
            await eng.query(slow, timeout_s=60)
            single = time.perf_counter() - t0
            t1 = time.perf_counter()
            await asyncio.gather(eng.query(slow, timeout_s=60), eng.query(slow, timeout_s=60))
            pair = time.perf_counter() - t1
            return single, pair

        single, pair = asyncio.run(main())
        # Serialized -> pair ~= 2x single. Concurrent -> pair ~= single.
        assert pair < single * 1.7, f"pair={pair:.2f}s single={single:.2f}s (looks serialized)"
    finally:
        eng.close()


def test_cursor_read_is_correct_and_has_spill_pragma(tmp_path):
    eng = _engine(tmp_path)
    try:
        res = asyncio.run(eng.query("SELECT current_setting('temp_directory') AS t"))
        assert str(tmp_path) in str(res.rows[0][0])  # spill pragma applied on the cursor
        prov = asyncio.run(eng.query("SELECT org FROM crm.accounts ORDER BY id"))
        assert [r[0] for r in prov.rows] == ["acme", "beta"]
        assert prov.provenance is not None
    finally:
        eng.close()


def test_timeout_still_fires(tmp_path):
    eng = _engine(tmp_path)
    try:
        with pytest.raises(QueryTimeout):
            asyncio.run(eng.query("SELECT count(*) FROM range(9000000000000)", timeout_s=0.5))
    finally:
        eng.close()
