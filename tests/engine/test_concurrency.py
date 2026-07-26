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
    # A trivial fast query must not be blocked behind a slow one. This tests the
    # lock (not CPU speedup), so it holds even on a 2-core CI runner where two
    # CPU-bound queries wouldn't parallelize in wall-clock terms.
    eng = _engine(tmp_path)
    slow = "SELECT count(*) FROM range(2000000000) t(x) WHERE x % 7 = 3"
    try:

        async def main():
            slow_task = asyncio.create_task(eng.query(slow, timeout_s=60))
            await asyncio.sleep(0.3)  # let the slow query start
            t0 = time.perf_counter()
            fast = await eng.query("SELECT 1 AS one", timeout_s=60)
            fast_elapsed = time.perf_counter() - t0
            slow_running = not slow_task.done()  # was the slow query still in flight?
            await slow_task
            return fast, fast_elapsed, slow_running

        fast, fast_elapsed, slow_running = asyncio.run(main())
        assert fast.rows[0][0] == 1
        assert slow_running, "slow query already finished; can't prove overlap"
        assert fast_elapsed < 1.0, f"fast blocked {fast_elapsed:.2f}s behind the slow query"
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
