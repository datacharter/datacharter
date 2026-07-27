import pytest

from datacharter.contracts import CharterError, load_charter


def write_charter(tmp_path, text):
    (tmp_path / "charter.yaml").write_text(text)
    return tmp_path


def test_minimal_file_source_loads(tmp_path):
    text = "version: 1\nsources:\n  plans:\n    type: csv\n    path: data/plans.csv\n"
    ws = write_charter(tmp_path, text)
    charter = load_charter(ws)
    assert charter.sources[0].name == "plans"
    assert charter.warnings == []


def test_empty_sources_loads_as_fresh_workspace(tmp_path):
    # `datacharter init` scaffolds `sources: {}`; a fresh workspace must be servable
    # (sources are added later, via charter.yaml or the in-app source manager).
    charter = load_charter(write_charter(tmp_path, "version: 1\nsources: {}\n"))
    assert charter.sources == []


def test_null_sources_loads_as_empty(tmp_path):
    charter = load_charter(write_charter(tmp_path, "version: 1\nsources:\n"))
    assert charter.sources == []


def test_non_mapping_sources_rejected(tmp_path):
    ws = write_charter(tmp_path, "version: 1\nsources:\n  - a\n  - b\n")
    with pytest.raises(CharterError, match=r"'sources' must be a mapping"):
        load_charter(ws)


def test_env_reference_resolution(tmp_path, monkeypatch):
    monkeypatch.setenv("PG_PW", "resolved-pw-value")
    ws = write_charter(
        tmp_path,
        """
version: 1
sources:
  crm:
    type: postgres
    connection: {host: h, database: d, user: u}
    credentials:
      password: ${PG_PW}
""",
    )
    charter = load_charter(ws)
    assert charter.sources[0].credentials["password"] == "resolved-pw-value"


def test_dotenv_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("FILE_PW", raising=False)
    (tmp_path / ".env").write_text("FILE_PW=from-dotenv\n")
    ws = write_charter(
        tmp_path,
        """
version: 1
sources:
  crm:
    type: postgres
    connection: {host: h, database: d, user: u}
    credentials:
      password: ${FILE_PW}
""",
    )
    assert load_charter(ws).sources[0].credentials["password"] == "from-dotenv"


def test_keyring_fallback(tmp_path, monkeypatch):
    import keyring

    monkeypatch.delenv("KR_PW", raising=False)
    monkeypatch.setattr(
        keyring, "get_password", lambda svc, name: "from-keyring" if name == "KR_PW" else None
    )
    ws = write_charter(
        tmp_path,
        """
version: 1
sources:
  crm:
    type: postgres
    connection: {host: h, database: d, user: u}
    credentials:
      password: ${KR_PW}
""",
    )
    assert load_charter(ws).sources[0].credentials["password"] == "from-keyring"


def test_literal_credential_hard_errors(tmp_path):
    ws = write_charter(
        tmp_path,
        """
version: 1
sources:
  crm:
    type: postgres
    connection: {host: h, database: d, user: u}
    credentials: {password: hunter2}
""",
    )
    with pytest.raises(CharterError, match=r"literal values are not allowed"):
        load_charter(ws)


def test_credential_shaped_connection_key_errors(tmp_path):
    ws = write_charter(
        tmp_path,
        """
version: 1
sources:
  crm:
    type: postgres
    connection: {host: h, database: d, user: u, password: oops}
""",
    )
    with pytest.raises(CharterError, match=r"connection\.password"):
        load_charter(ws)


def test_unresolvable_reference_lists_stores_tried(tmp_path, monkeypatch):
    monkeypatch.delenv("NOPE_X", raising=False)
    ws = write_charter(
        tmp_path,
        """
version: 1
sources:
  crm:
    type: postgres
    connection: {host: h, database: d, user: u}
    credentials:
      password: ${NOPE_X}
""",
    )
    with pytest.raises(CharterError, match=r"environment"):
        load_charter(ws)


def test_absolute_path_warns(tmp_path):
    text = "version: 1\nsources:\n  f:\n    type: csv\n    path: /abs/x.csv\n"
    charter = load_charter(write_charter(tmp_path, text))
    assert any("absolute path" in w for w in charter.warnings)


def test_backslash_path_warns(tmp_path):
    text = 'version: 1\nsources:\n  f:\n    type: csv\n    path: "data\\\\x.csv"\n'
    assert any("POSIX" in w for w in load_charter(write_charter(tmp_path, text)).warnings)


def test_s3_url_does_not_warn(tmp_path):
    ws = write_charter(tmp_path, "version: 1\nsources:\n  f:\n    type: parquet\n    path: s3://b/x\n")
    assert load_charter(ws).warnings == []


def test_inline_var_in_path(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", "data")
    text = "version: 1\nsources:\n  f:\n    type: csv\n    path: ${DATA_DIR}/x.csv\n"
    assert load_charter(write_charter(tmp_path, text)).sources[0].path == "data/x.csv"


def test_unknown_type_lists_valid_ones(tmp_path):
    ws = write_charter(tmp_path, "version: 1\nsources:\n  f:\n    type: oracle\n    path: x\n")
    with pytest.raises(CharterError, match=r"is not one of: postgres"):
        load_charter(ws)


def test_bad_source_name_has_context(tmp_path):
    text = "version: 1\nsources:\n  Bad-Name:\n    type: csv\n    path: x.csv\n"
    with pytest.raises(CharterError, match=r"sources\.Bad-Name"):
        load_charter(write_charter(tmp_path, text))


def test_missing_file_suggests_init(tmp_path):
    with pytest.raises(CharterError, match=r"datacharter init"):
        load_charter(tmp_path)


def test_wrong_version_rejected(tmp_path):
    ws = write_charter(tmp_path, "version: 2\nsources:\n  f:\n    type: csv\n    path: x.csv\n")
    with pytest.raises(CharterError, match=r"unsupported version"):
        load_charter(ws)


def test_loader_parses_row_filters(tmp_path):
    from datacharter.contracts import load_charter

    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "o.csv").write_text("a,region\n1,US\n")
    (tmp_path / "charter.yaml").write_text(
        "version: 1\nsources:\n  store:\n    type: csv\n    path: data/o.csv\n"
        "    row_filters:\n      o: \"region = 'US'\"\n"
    )
    charter = load_charter(tmp_path)
    assert charter.sources[0].row_filters == {"o": "region = 'US'"}


def test_loader_parses_metric_joins_and_time_column(tmp_path):
    from datacharter.contracts import load_charter

    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "o.csv").write_text("customer_id,total,created_at\n1,10,2024-01-01\n")
    (tmp_path / "charter.yaml").write_text(
        "version: 1\n"
        "sources:\n  o:\n    type: csv\n    path: data/o.csv\n"
        "metrics:\n"
        "  revenue:\n"
        "    relation: o\n"
        "    expression: sum(total)\n"
        "    time_column: created_at\n"
        "    joins:\n"
        "      - relation: c\n"
        "        on: o.customer_id = c.id\n"
        "        type: left\n"
    )
    m = load_charter(tmp_path).metrics[0]
    assert m.time_column == "created_at"
    assert m.joins[0].relation == "c"
    assert m.joins[0].type == "left"
    assert m.joins[0].on == "o.customer_id = c.id"


def test_loader_parses_tests(tmp_path):
    from datacharter.contracts import load_charter

    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "o.csv").write_text("id\n1\n")
    (tmp_path / "charter.yaml").write_text(
        "version: 1\nsources:\n  o:\n    type: csv\n    path: data/o.csv\n"
        "tests:\n  id_not_null:\n    type: not_null\n    relation: o\n    column: id\n"
    )
    t = load_charter(tmp_path).tests[0]
    assert t.name == "id_not_null"
    assert t.type == "not_null"
    assert t.column == "id"
