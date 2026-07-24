import sqlite3

import keyring
import keyring.backend
import pytest

from datacharter.engine.session import Engine
from datacharter.server import source_admin as admin


class _MemKeyring(keyring.backend.KeyringBackend):
    priority = 1

    def __init__(self):
        self.store = {}

    def get_password(self, service, name):
        return self.store.get((service, name))

    def set_password(self, service, name, value):
        self.store[(service, name)] = value

    def delete_password(self, service, name):
        self.store.pop((service, name), None)


@pytest.fixture
def mem_keyring():
    prev = keyring.get_keyring()
    keyring.set_keyring(_MemKeyring())
    yield keyring
    keyring.set_keyring(prev)


def _sqlite_form(tmp_path):
    con = sqlite3.connect(tmp_path / "crm.db")
    con.execute("CREATE TABLE accounts (id INTEGER, org TEXT)")
    con.commit()
    con.close()
    return admin.SourceForm(name="crm", type="sqlite", path="crm.db", tables=["accounts"])


def test_create_writes_ref_not_literal(tmp_path, mem_keyring):
    (tmp_path / "charter.yaml").write_text("version: 1\nsources: {}\n")
    form = admin.SourceForm(
        name="crmpg",
        type="postgres",
        connection={"host": "localhost", "port": 5432, "database": "d", "user": "u"},
        password="s3cret",
    )
    with Engine(tmp_path) as eng:
        admin.create_source(eng, tmp_path, form, apply_to_engine=False)
    text = (tmp_path / "charter.yaml").read_text()
    assert "s3cret" not in text  # never a literal (D7)
    assert "${CRMPG_PASSWORD}" in text
    assert mem_keyring.get_password("datacharter", "CRMPG_PASSWORD") == "s3cret"


def test_create_and_delete_sqlite_round_trip(tmp_path, mem_keyring):
    (tmp_path / "charter.yaml").write_text("version: 1\nsources: {}\n")
    form = _sqlite_form(tmp_path)
    with Engine(tmp_path) as eng:
        admin.create_source(eng, tmp_path, form)
        assert any(s.name == "crm" for s in eng.sources)
        assert "crm" in (tmp_path / "charter.yaml").read_text()
        admin.delete_source(eng, tmp_path, "crm")
        assert all(s.name != "crm" for s in eng.sources)
        assert "crm" not in (tmp_path / "charter.yaml").read_text()
