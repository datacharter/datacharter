"""`datacharter secrets set|list|rm` against an in-memory keyring backend."""

import keyring
import keyring.backend
import pytest

from datacharter.cli import main as cli_main


class _MemKeyring(keyring.backend.KeyringBackend):
    priority = 1

    def __init__(self):
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service, name):
        return self.store.get((service, name))

    def set_password(self, service, name, value):
        self.store[(service, name)] = value

    def delete_password(self, service, name):
        self.store.pop((service, name), None)


@pytest.fixture
def mem_keyring():
    previous = keyring.get_keyring()
    keyring.set_keyring(_MemKeyring())
    yield
    keyring.set_keyring(previous)


def test_set_list_rm_roundtrip(mem_keyring, capsys):
    assert cli_main(["secrets", "set", "PGPASS", "--value", "s3cret"]) == 0
    assert keyring.get_password("datacharter", "PGPASS") == "s3cret"

    assert cli_main(["secrets", "list"]) == 0
    assert "PGPASS" in capsys.readouterr().out

    assert cli_main(["secrets", "rm", "PGPASS"]) == 0
    assert keyring.get_password("datacharter", "PGPASS") is None

    capsys.readouterr()  # drop the 'Removed' line before checking list output
    cli_main(["secrets", "list"])
    assert "PGPASS" not in capsys.readouterr().out


def test_set_requires_a_value(mem_keyring):
    assert cli_main(["secrets", "set", "EMPTY", "--value", ""]) == 1


def test_index_excludes_reserved_key(mem_keyring, capsys):
    cli_main(["secrets", "set", "A", "--value", "1"])
    cli_main(["secrets", "set", "B", "--value", "2"])
    capsys.readouterr()  # drop the 'Stored' lines
    cli_main(["secrets", "list"])
    listed = set(capsys.readouterr().out.split())
    assert listed == {"A", "B"}  # the internal index key must not appear
