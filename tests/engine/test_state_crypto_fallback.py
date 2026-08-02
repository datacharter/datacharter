"""A build without DuckDB's crypto module must still start — loudly unencrypted."""

import pytest

from datacharter.engine.session import Engine, EngineError


def _engine(tmp_path):
    return Engine(tmp_path, [], local_key="k" * 32)


def test_falls_back_to_unencrypted_when_crypto_missing(tmp_path, monkeypatch, capsys):
    eng = _engine(tmp_path)
    real_setup = Engine._setup
    calls = {"n": 0}

    def fake_setup(self, stmt):
        if "ENCRYPTION_KEY" in stmt:
            calls["n"] += 1
            raise EngineError("DuckDB currently has a read-only crypto module loaded")
        return real_setup(self, stmt)

    monkeypatch.setattr(Engine, "_setup", fake_setup)
    monkeypatch.setattr(Engine, "_load_crypto_module", lambda self: False)
    eng.start()
    try:
        assert calls["n"] == 1
        assert eng.state_encrypted is False
        assert "unencrypted" in capsys.readouterr().err
        assert eng.query_sync("SELECT 1 AS n").rows == [(1,)]
    finally:
        eng.close()


def test_retries_encrypted_after_loading_crypto(tmp_path, monkeypatch):
    eng = _engine(tmp_path)
    real_setup = Engine._setup
    state = {"loaded": False, "attempts": 0}

    def fake_setup(self, stmt):
        if "ENCRYPTION_KEY" in stmt:
            state["attempts"] += 1
            if not state["loaded"]:
                raise EngineError("read-only crypto module loaded")
            return real_setup(self, stmt[: stmt.index(" (ENCRYPTION_KEY")])
        return real_setup(self, stmt)

    def fake_load(self):
        state["loaded"] = True
        return True

    monkeypatch.setattr(Engine, "_setup", fake_setup)
    monkeypatch.setattr(Engine, "_load_crypto_module", fake_load)
    eng.start()
    try:
        assert state["attempts"] == 2
        assert eng.state_encrypted is True
    finally:
        eng.close()


def test_existing_db_with_wrong_key_still_errors(tmp_path):
    eng = _engine(tmp_path)
    eng.start()
    eng.close()
    other = Engine(tmp_path, [], local_key="z" * 32)
    with pytest.raises(EngineError, match="encryption key may have changed"):
        other.start()
