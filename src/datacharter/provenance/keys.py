"""Ed25519 signing keys for answer-provenance receipts.

A workspace holds one keypair under `.datacharter/keys/`. The private seed signs
receipts; the public key is published so any third party can verify a receipt
without trusting — or even contacting — the operator. Keys are raw 32-byte values
stored hex-encoded; the private file is written 0600.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

__all__ = [
    "Signer",
    "ProvenanceKeyError",
    "generate",
    "load_signer",
    "load_public",
    "fingerprint",
    "verify",
    "key_dir",
]

KEY_DIR = ".datacharter/keys"
_PRIV = "provenance.key"
_PUB = "provenance.pub"


class ProvenanceKeyError(Exception):
    """A signing key is missing, malformed, or would be overwritten."""


def key_dir(workspace: Path | str) -> Path:
    return Path(workspace) / KEY_DIR


def fingerprint(public_raw: bytes) -> str:
    """Short, stable key id: the first 16 hex chars of SHA-256 over the public key."""
    return hashlib.sha256(public_raw).hexdigest()[:16]


class Signer:
    """Wraps a private key; exposes the public key and a signing method."""

    def __init__(self, private: Ed25519PrivateKey) -> None:
        self._priv = private
        self._pub_raw = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)

    @property
    def public_raw(self) -> bytes:
        return self._pub_raw

    @property
    def public_hex(self) -> str:
        return self._pub_raw.hex()

    @property
    def key_id(self) -> str:
        return fingerprint(self._pub_raw)

    def sign(self, data: bytes) -> bytes:
        return self._priv.sign(data)


def generate(workspace: Path | str, *, force: bool = False) -> Signer:
    """Create and store a new keypair. Refuses to clobber an existing key unless
    forced — replacing a key invalidates the pinning of every receipt it signed."""
    d = key_dir(workspace)
    d.mkdir(parents=True, exist_ok=True)
    priv_path = d / _PRIV
    if priv_path.exists() and not force:
        raise ProvenanceKeyError(
            f"A signing key already exists at {priv_path}. Use --force to replace "
            "it — this invalidates the key pinning of every receipt it has signed."
        )
    priv = Ed25519PrivateKey.generate()
    seed = priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    priv_path.write_text(seed.hex() + "\n")
    os.chmod(priv_path, 0o600)
    pub_raw = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    (d / _PUB).write_text(pub_raw.hex() + "\n")
    return Signer(priv)


def load_signer(workspace: Path | str) -> Signer:
    priv_path = key_dir(workspace) / _PRIV
    if not priv_path.exists():
        raise ProvenanceKeyError(
            f"No signing key at {priv_path}. Run `datacharter provenance keygen` first."
        )
    try:
        seed = bytes.fromhex(priv_path.read_text().strip())
        return Signer(Ed25519PrivateKey.from_private_bytes(seed))
    except (ValueError, TypeError) as exc:
        raise ProvenanceKeyError(f"Signing key at {priv_path} is malformed: {exc}") from exc


def load_public(workspace: Path | str) -> bytes | None:
    p = key_dir(workspace) / _PUB
    if not p.exists():
        return None
    return bytes.fromhex(p.read_text().strip())


def verify(public_raw: bytes, signature: bytes, data: bytes) -> bool:
    """True iff `signature` is a valid Ed25519 signature over `data` for the key."""
    try:
        Ed25519PublicKey.from_public_bytes(public_raw).verify(signature, data)
        return True
    except Exception:  # noqa: BLE001 — any failure is a failed verification
        return False
