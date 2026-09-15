"""User cancel: interrupt() stops an in-flight query and leaves the session usable."""

import asyncio
import threading
import time

import pytest

from datacharter.engine.session import Engine, QueryCancelled

_SLOW = "SELECT count(*) FROM range(1000000000) a, range(1000) b"


def test_interrupt_cancels_query_sync(tmp_path):
    with Engine(tmp_path) as eng:
        caught: list[BaseException] = []

        def run() -> None:
            try:
                eng.query_sync(_SLOW)
            except BaseException as exc:
                caught.append(exc)

        thread = threading.Thread(target=run)
        thread.start()
        time.sleep(0.25)
        eng.interrupt()
        thread.join(timeout=8)
        assert not thread.is_alive()
        assert caught and isinstance(caught[0], QueryCancelled)
        assert eng.query_sync("SELECT 1").rows == [(1,)]


async def test_interrupt_cancels_async_query(tmp_path):
    with Engine(tmp_path) as eng:

        async def slow() -> None:
            await eng.query(_SLOW, timeout_s=30)

        task = asyncio.create_task(slow())
        await asyncio.sleep(0.25)
        eng.interrupt()
        with pytest.raises(QueryCancelled):
            await task
        assert eng.query_sync("SELECT 1").rows == [(1,)]
