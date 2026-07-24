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
    ws = write_charter(tmp_path, "version: 1\nsources:\n  f:\n    type: excel\n    path: x.xlsx\n")
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
