"""The answer-provenance receipt: a signed, portable seal over one governed answer.

A receipt has three parts:

- ``body`` — the sealed facts: the question, the governed queries (SQL + relations
  read + masked columns + row count + a hash of the exact result the surface
  returned), the governance ``surface_hash`` (the policy version in force), the
  principal, the model, a timestamp, the answer hash, and a Merkle link to the
  tamper-evident audit chain (``audit.head``).
- ``content_hash`` — SHA-256 over the canonical body, for a quick integrity check.
- ``signature`` — an Ed25519 signature over the canonical body, plus the public
  key and its fingerprint, so anyone can verify authenticity offline.

Canonicalization matches the audit recorder (`sort_keys`, tight separators) so the
same bytes hash the same everywhere.
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime

from datacharter.provenance import keys

__all__ = ["SCHEMA", "build_body", "sign", "verify", "content_hash", "verify_audit_link"]

SCHEMA = "datacharter.provenance/v1"


def _canonical(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()


def content_hash(body: dict) -> str:
    """SHA-256 over the canonical body."""
    return hashlib.sha256(_canonical(body)).hexdigest()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def build_body(
    *,
    workspace: str,
    surface_hash: str,
    principal: str | None,
    model: str | None,
    question: str | None,
    queries: list[dict],
    answer: str | None,
    audit: dict | None,
    issued_at: str | None = None,
) -> dict:
    """Assemble the sealed body. `queries` items are
    `{sql, relations, masked_columns, row_count, result_sha256}`."""
    return {
        "schema": SCHEMA,
        "issued_at": issued_at or _now_iso(),
        "workspace": workspace,
        "principal": principal,
        "model": model,
        "question": question,
        "surface_hash": surface_hash,
        "queries": queries,
        "answer_sha256": (
            hashlib.sha256(answer.encode()).hexdigest() if answer is not None else None
        ),
        "audit": audit,
    }


def sign(body: dict, signer: keys.Signer) -> dict:
    """Wrap a body into a signed receipt."""
    return {
        "body": body,
        "content_hash": content_hash(body),
        "signature": {
            "alg": "ed25519",
            "key_id": signer.key_id,
            "public_key": signer.public_hex,
            "sig": base64.b64encode(signer.sign(_canonical(body))).decode(),
        },
    }


def verify(receipt: dict, *, expected_pubkey: str | None = None) -> dict:
    """Check a receipt's integrity and signature offline.

    Returns `{ok, checks, key_id, public_key}`. `checks` always includes
    `content_hash` and `signature`; `key_match` is added when `expected_pubkey`
    is given (pin the receipt to a key you trust out-of-band)."""
    checks: dict[str, bool] = {}
    body = receipt.get("body")
    sig_block = receipt.get("signature") or {}
    pub_hex = sig_block.get("public_key")

    checks["content_hash"] = (
        isinstance(body, dict) and content_hash(body) == receipt.get("content_hash")
    )

    ok_sig = False
    if isinstance(body, dict) and pub_hex and sig_block.get("sig"):
        try:
            ok_sig = keys.verify(
                bytes.fromhex(pub_hex),
                base64.b64decode(sig_block["sig"]),
                _canonical(body),
            )
        except (ValueError, TypeError):
            ok_sig = False
    checks["signature"] = ok_sig

    if expected_pubkey is not None:
        checks["key_match"] = pub_hex == expected_pubkey

    return {
        "ok": all(checks.values()),
        "checks": checks,
        "key_id": sig_block.get("key_id"),
        "public_key": pub_hex,
    }


def verify_audit_link(receipt: dict, workspace: str) -> dict:
    """Optional: confirm the receipt's audit head is a real point in the workspace's
    audit chain, and that the chain itself verifies. Returns
    `{chain_ok, head_in_chain, detail}`."""
    from datacharter.audit.evidence import read_entries, verify_chain

    audit = (receipt.get("body") or {}).get("audit") or {}
    head = audit.get("head")
    chain_ok, _n, detail = verify_chain(workspace)
    known = {e.get("hash") for e in read_entries(workspace)}
    return {
        "chain_ok": chain_ok,
        "head_in_chain": bool(head) and head in known,
        "detail": detail,
    }
