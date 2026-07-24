"""Keyring-backed storage for charter ${NAME} credentials (D7)."""

from __future__ import annotations

import contextlib

from datacharter.contracts.resolve import KEYRING_SERVICE

__all__ = ["secret_ref_name", "store_secret", "delete_secret", "list_secrets"]

_INDEX_KEY = "__datacharter_index__"  # reserved key tracking stored names


def secret_ref_name(source: str, key: str) -> str:
    """`('crmpg', 'password')` -> `'CRMPG_PASSWORD'`."""
    return f"{source}_{key}".upper()


def _index(kr) -> list[str]:
    with contextlib.suppress(Exception):
        raw = kr.get_password(KEYRING_SERVICE, _INDEX_KEY)
        return [n for n in (raw or "").split(",") if n]
    return []


def store_secret(name: str, value: str) -> None:
    import keyring  # noqa: PLC0415

    keyring.set_password(KEYRING_SERVICE, name, value)
    names = sorted(set(_index(keyring)) | {name})
    with contextlib.suppress(Exception):
        keyring.set_password(KEYRING_SERVICE, _INDEX_KEY, ",".join(names))


def delete_secret(name: str) -> None:
    import keyring  # noqa: PLC0415

    with contextlib.suppress(Exception):
        keyring.delete_password(KEYRING_SERVICE, name)
    names = [n for n in _index(keyring) if n != name]
    with contextlib.suppress(Exception):
        keyring.set_password(KEYRING_SERVICE, _INDEX_KEY, ",".join(names))


def list_secrets() -> list[str]:
    import keyring  # noqa: PLC0415

    return _index(keyring)
