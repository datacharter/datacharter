"""One Snowflake connector is reused across queries and closed on lifecycle end; SSO passthrough."""

import sys

from datacharter.engine import snowflake as sf
from datacharter.engine.session import Engine
from datacharter.models import Source, SourceType


def test_connect_includes_authenticator_when_set(monkeypatch):
    captured = {}

    class _Connector:
        @staticmethod
        def connect(**kw):
            captured.update(kw)
            return object()

    class _Mod:
        connector = _Connector

    monkeypatch.setitem(sys.modules, "snowflake", _Mod)
    monkeypatch.setitem(sys.modules, "snowflake.connector", _Connector)
    src = Source(
        name="wh",
        type=SourceType.SNOWFLAKE,
        connection={"account": "x", "authenticator": "externalbrowser"},
    )
    sf._connect(src)
    assert captured.get("authenticator") == "externalbrowser"


class _Cur:
    description = [("id", 0, None, None, None, None, None)]

    def __init__(self):
        self._rows = [(1,)]
        self.executed = None

    def execute(self, s):
        self.executed = s

    def fetchmany(self, n):
        batch, self._rows = self._rows[:n], self._rows[n:]
        return batch

    def close(self):
        pass


class _Conn:
    def __init__(self):
        self.closed = False

    def cursor(self):
        return _Cur()

    def close(self):
        self.closed = True


def test_engine_reuses_one_connector(tmp_path, monkeypatch):
    calls = []

    def factory(_src):
        c = _Conn()
        calls.append(c)
        return c

    monkeypatch.setattr(sf, "_connect", factory)
    src = Source(name="wh", type=SourceType.SNOWFLAKE, connection={"account": "x"}, tables=["t"])
    eng = Engine(tmp_path, [src]).start()
    try:
        eng.query_sync("SELECT id FROM wh__t")
        eng.query_sync("SELECT id FROM wh__t WHERE id = 1")
        assert len(calls) == 1  # one connector reused, not reconnected per query
    finally:
        eng.close()
    assert calls[0].closed is True  # closed on Engine.close
