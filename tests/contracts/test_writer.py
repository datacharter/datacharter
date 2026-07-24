import pytest

from datacharter.contracts.writer import ContractWriteError, remove_source, upsert_source

BASE = """\
version: 1
sources:
  crmpg:  # our CRM
    type: postgres
    connection: {host: localhost, port: 5432, database: demo, user: charter, schema: public}
    credentials:
      password: ${CRMPG_PASSWORD}
    tables: [customers]
"""


def test_upsert_adds_source_and_preserves_comment(tmp_path):
    (tmp_path / "charter.yaml").write_text(BASE)
    upsert_source(
        tmp_path,
        "shopmy",
        {
            "type": "mysql",
            "connection": {
                "host": "localhost",
                "port": 3306,
                "database": "shop",
                "user": "charter",
            },
            "credentials": {"password": "${SHOPMY_PASSWORD}"},
            "tables": ["orders"],
        },
    )
    text = (tmp_path / "charter.yaml").read_text()
    assert "# our CRM" in text  # existing comment preserved
    assert "crmpg" in text and "shopmy" in text
    assert "${SHOPMY_PASSWORD}" in text


def test_upsert_updates_existing(tmp_path):
    (tmp_path / "charter.yaml").write_text(BASE)
    upsert_source(tmp_path, "crmpg", {"type": "postgres", "connection": {}, "tables": ["a", "b"]})
    text = (tmp_path / "charter.yaml").read_text()
    assert "a" in text and "b" in text


def test_remove_drops_source(tmp_path):
    (tmp_path / "charter.yaml").write_text(BASE)
    remove_source(tmp_path, "crmpg")
    assert "crmpg" not in (tmp_path / "charter.yaml").read_text()


def test_rejects_literal_credential(tmp_path):
    (tmp_path / "charter.yaml").write_text(BASE)
    with pytest.raises(ContractWriteError):
        upsert_source(tmp_path, "x", {"type": "postgres", "credentials": {"password": "hunter2"}})
