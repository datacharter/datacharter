"""Self-Defending Data: ship rows inside a signed policy envelope so the charter
*follows the data* out of the workspace — into agent memory, a cache, a ticket, a
downstream tool. Opening the envelope re-asserts the policy every time.

Three properties travel with the bytes:
- **Tamper-evident** — the envelope is signed; a single altered byte fails to open.
- **Already masked** — PII was masked at seal time, so the raw values are never in
  the payload to begin with.
- **Self-expiring** — past the TTL the payload self-redacts on open; stale exports
  stop being readable without anyone revoking them.

The envelope is a provenance receipt (same Ed25519 signing + verification), so it
verifies with the very same offline checks.
"""

from __future__ import annotations

from datetime import UTC, datetime

from datacharter.provenance import keys, receipt

__all__ = ["SCHEMA", "REDACTED", "build_envelope", "open_envelope"]

SCHEMA = "datacharter/self-defending/v1"
REDACTED = "⛔[expired]"


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def build_envelope(
    *, workspace: str, surface_hash: str, columns: list[str], rows: list[list],
    masked_columns: list[str], signer: keys.Signer, ttl_seconds: int | None,
    issued_at: str | None = None,
) -> dict:
    """Assemble and sign a self-defending envelope. `rows` must already be masked."""
    issued = issued_at or receipt._now_iso()
    expires = None
    if ttl_seconds is not None:
        expires = (_parse_iso(issued) + _td(ttl_seconds)).isoformat()
    body = {
        "schema": SCHEMA,
        "policy": {
            "issued_at": issued,
            "expires_at": expires,
            "workspace": workspace,
            "surface_hash": surface_hash,
            "masked_columns": sorted(masked_columns),
        },
        "data": {"columns": list(columns), "rows": [list(r) for r in rows]},
    }
    return receipt.sign(body, signer)


def _td(seconds: int):
    from datetime import timedelta
    return timedelta(seconds=seconds)


def open_envelope(env: dict, *, now: datetime | None = None,
                  expected_pubkey: str | None = None) -> dict:
    """Verify + open an envelope. Returns
    `{ok, tampered, expired, columns, rows, policy, checks}`. On expiry every cell
    is redacted; on tamper the payload is withheld entirely."""
    verdict = receipt.verify(env, expected_pubkey=expected_pubkey)
    body = env.get("body") or {}
    policy = body.get("policy") or {}
    data = body.get("data") or {}
    columns = list(data.get("columns") or [])

    if not verdict["ok"]:
        return {"ok": False, "tampered": True, "expired": False, "columns": columns,
                "rows": [], "policy": policy, "checks": verdict["checks"]}

    now = now or datetime.now(UTC)
    expires = policy.get("expires_at")
    expired = bool(expires) and now > _parse_iso(expires)
    rows = [list(r) for r in (data.get("rows") or [])]
    if expired:
        rows = [[REDACTED for _ in columns] for _ in rows]
    return {"ok": not expired, "tampered": False, "expired": expired, "columns": columns,
            "rows": rows, "policy": policy, "checks": verdict["checks"]}
