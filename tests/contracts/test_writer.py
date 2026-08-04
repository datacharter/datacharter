import pytest

from datacharter.contracts.writer import (
    ContractWriteError,
    remove_source,
    set_agent_access,
    upsert_source,
)

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


def _reload(tmp_path):
    from ruamel.yaml import YAML

    return YAML().load((tmp_path / "charter.yaml").read_text())


def test_set_agent_access_field_table_source_levels(tmp_path):
    (tmp_path / "charter.yaml").write_text(BASE)
    set_agent_access(tmp_path, "crmpg", "customers", "email", True)  # field
    aa = _reload(tmp_path)["sources"]["crmpg"]["agent_access"]
    assert aa["columns"]["customers.email"] is True
    set_agent_access(tmp_path, "crmpg", "customers", None, False)  # table
    aa = _reload(tmp_path)["sources"]["crmpg"]["agent_access"]
    assert aa["tables"]["customers"] is False
    set_agent_access(tmp_path, "crmpg", None, None, True)  # source
    aa = _reload(tmp_path)["sources"]["crmpg"]["agent_access"]
    assert aa["source"] is True
    # other fields preserved
    assert list(_reload(tmp_path)["sources"]["crmpg"]["tables"]) == ["customers"]


def test_coarser_access_toggle_clears_finer_overrides(tmp_path):
    # a table toggle must clear that table's field overrides (else a stale
    # field override wins and "mask the table" leaves a PII column visible);
    # a source toggle clears everything beneath it.
    (tmp_path / "charter.yaml").write_text(BASE)
    set_agent_access(tmp_path, "crmpg", "customers", "email", True)
    set_agent_access(tmp_path, "crmpg", "customers", None, False)
    aa = _reload(tmp_path)["sources"]["crmpg"]["agent_access"]
    assert "customers.email" not in (aa.get("columns") or {})
    assert aa["tables"]["customers"] is False

    set_agent_access(tmp_path, "crmpg", "customers", "email", True)
    set_agent_access(tmp_path, "crmpg", None, None, False)
    aa = _reload(tmp_path)["sources"]["crmpg"]["agent_access"]
    assert "columns" not in aa and "tables" not in aa
    assert aa["source"] is False


def test_set_agent_access_unknown_source(tmp_path):
    (tmp_path / "charter.yaml").write_text(BASE)
    with pytest.raises(ContractWriteError):
        set_agent_access(tmp_path, "ghost", "t", "c", True)


def test_set_agent_access_local_writes_top_level(tmp_path):
    (tmp_path / "charter.yaml").write_text(BASE)
    set_agent_access(tmp_path, "local", "snap", "email", True)  # snapshot field
    la = _reload(tmp_path)["local_access"]
    assert la["columns"]["snap.email"] is True
    assert "local" not in (_reload(tmp_path).get("sources") or {})  # not a fake source


def test_upsert_source_preserves_governance_keys(tmp_path):
    # F-6: editing a source (e.g. changing a hostname) silently ERASED
    # agent_access, row_filters, and context — row-level security dropped by a
    # connection edit. Governance must survive unless explicitly replaced.
    (tmp_path / "charter.yaml").write_text(
        "version: 1\n"
        "sources:\n"
        "  crm:\n"
        "    type: csv\n"
        "    path: a.csv\n"
        "    agent_access:\n      columns:\n        people.email: false\n"
        "    row_filters:\n      people: \"region = 'US'\"\n"
        "    context:\n      people: one row per person\n"
    )
    upsert_source(tmp_path, "crm", {"type": "csv", "path": "b.csv"})
    body = _reload(tmp_path)["sources"]["crm"]
    assert body["path"] == "b.csv"
    assert body["agent_access"]["columns"]["people.email"] is False
    assert body["row_filters"]["people"] == "region = 'US'"
    assert body["context"]["people"] == "one row per person"
