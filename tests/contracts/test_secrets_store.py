import keyring
import keyring.backend
import pytest

from datacharter.contracts import secrets as secretstore


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
    prev = keyring.get_keyring()
    keyring.set_keyring(_MemKeyring())
    yield
    keyring.set_keyring(prev)


def test_secret_ref_name():
    assert secretstore.secret_ref_name("crmpg", "password") == "CRMPG_PASSWORD"


def test_store_list_delete(mem_keyring):
    secretstore.store_secret("CRMPG_PASSWORD", "s3cret")
    assert keyring.get_password("datacharter", "CRMPG_PASSWORD") == "s3cret"
    assert secretstore.list_secrets() == ["CRMPG_PASSWORD"]
    secretstore.delete_secret("CRMPG_PASSWORD")
    assert keyring.get_password("datacharter", "CRMPG_PASSWORD") is None
    assert secretstore.list_secrets() == []
