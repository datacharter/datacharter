"""DuckDB resource bounds: memory_limit + threads, so a heavy query spills or
errors within budget instead of OOM-killing the container."""

from datacharter.engine import session
from datacharter.engine.session import Engine, _duckdb_memory_limit


def _setting(eng, name):
    return eng._conn.execute(f"SELECT current_setting('{name}')").fetchone()[0]


def test_memory_limit_env_override_takes_effect(tmp_path, monkeypatch):
    monkeypatch.setenv("DATACHARTER_DUCKDB_MEMORY_LIMIT", "256MB")
    with Engine(tmp_path, []) as eng:
        # DuckDB normalizes 256MB (256e6 bytes) to ~244.1 MiB.
        assert "244" in _setting(eng, "memory_limit")


def test_threads_env_pins_threads(tmp_path, monkeypatch):
    monkeypatch.setenv("DATACHARTER_DUCKDB_THREADS", "2")
    with Engine(tmp_path, []) as eng:
        assert _setting(eng, "threads") == 2


def test_invalid_threads_is_ignored_not_fatal(tmp_path, monkeypatch):
    monkeypatch.setenv("DATACHARTER_DUCKDB_THREADS", "not-a-number")
    with Engine(tmp_path, []) as eng:  # must still start cleanly
        assert int(_setting(eng, "threads")) >= 1  # left at DuckDB's default


def test_duckdb_memory_limit_prefers_env_over_cgroup(monkeypatch):
    monkeypatch.setenv("DATACHARTER_DUCKDB_MEMORY_LIMIT", "1GB")
    monkeypatch.setattr(session, "_cgroup_memory_bytes", lambda: 8 * 1024**3)
    assert _duckdb_memory_limit() == "1GB"


def test_duckdb_memory_limit_derives_80pct_of_cgroup(monkeypatch):
    monkeypatch.delenv("DATACHARTER_DUCKDB_MEMORY_LIMIT", raising=False)
    monkeypatch.setattr(session, "_cgroup_memory_bytes", lambda: 1024**3)  # 1 GiB
    # 80% of 1 GiB = 819.2 MiB -> floor to MB
    assert _duckdb_memory_limit() == "819MB"


def test_duckdb_memory_limit_none_on_bare_metal(monkeypatch):
    monkeypatch.delenv("DATACHARTER_DUCKDB_MEMORY_LIMIT", raising=False)
    monkeypatch.setattr(session, "_cgroup_memory_bytes", lambda: None)
    assert _duckdb_memory_limit() is None  # leaves DuckDB's own default
