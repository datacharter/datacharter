"""principals: and grants: identities in git, default-deny on the MCP HTTP surface."""

from __future__ import annotations

from dataclasses import dataclass

from datacharter.contracts.loader_errors import CharterError
from datacharter.mcp.auth import Principal

__all__ = [
    "PrincipalRef",
    "CharterPolicy",
    "parse_principals",
    "parse_grants",
    "policy_from_charter",
]


@dataclass(frozen=True)
class PrincipalRef:
    """A named identity in charter.yaml, matched to a token `sub`."""

    sub: str
    roles: tuple[str, ...] = ()


def parse_principals(raw: object, ctx: str) -> dict[str, PrincipalRef]:
    if raw in (None, {}):
        return {}
    if not isinstance(raw, dict):
        raise CharterError(f"{ctx}: 'principals' must be a mapping of name -> identity.")
    out: dict[str, PrincipalRef] = {}
    for name, body in raw.items():
        key = str(name)
        if isinstance(body, str) and body.strip():
            out[key] = PrincipalRef(sub=body.strip())
            continue
        if not isinstance(body, dict) or not str(body.get("sub") or "").strip():
            raise CharterError(
                f"{ctx}: principals.{key} must be a subject string or {{sub: ..., roles?: []}}."
            )
        roles = body.get("roles") or []
        if not isinstance(roles, list) or not all(isinstance(r, str) for r in roles):
            raise CharterError(f"{ctx}: principals.{key}.roles must be a list of strings.")
        out[key] = PrincipalRef(sub=str(body["sub"]).strip(), roles=tuple(roles))
    return out


def parse_grants(raw: object, ctx: str) -> dict[str, list[str]]:
    if raw in (None, {}):
        return {}
    if not isinstance(raw, dict):
        raise CharterError(f"{ctx}: 'grants' must be a mapping of principal -> relations.")
    out: dict[str, list[str]] = {}
    for name, body in raw.items():
        if not isinstance(body, list) or not all(isinstance(g, str) and g.strip() for g in body):
            raise CharterError(
                f"{ctx}: grants.{name} must be a list of relation strings "
                "(store.orders, store.customers.tier, store.*, *)."
            )
        out[str(name)] = [g.strip() for g in body]
    return out


def policy_from_charter(charter) -> CharterPolicy | None:
    if not getattr(charter, "grants", None):
        return None
    return CharterPolicy(charter.principals, charter.grants)


def _covers(grant: str, source: str, table: str | None, column: str | None) -> bool:
    g = grant.lower().strip()
    src = (source or "").lower()
    tbl = (table or "").lower() if table is not None else None
    col = (column or "").lower() if column is not None else None
    if g == "*":
        return True
    parts = g.split(".")
    if parts[0] not in {src, "*"}:
        return False
    if len(parts) == 1:
        return True
    if parts[1] == "*":
        return True
    if tbl is None:
        return True
    if parts[1] != tbl:
        return False
    if len(parts) == 2:
        return True
    if col is None:
        return True
    return parts[2] == col


class CharterPolicy:
    """Default-deny grants keyed by principal name, sub, or JWT role."""

    def __init__(
        self,
        principals: dict[str, PrincipalRef],
        grants: dict[str, list[str]],
    ) -> None:
        self.principals = principals
        self.grants = {k: [g.lower() for g in v] for k, v in grants.items()}

    def identities(self, principal: Principal) -> set[str]:
        sub = (principal.subject or "").strip()
        if not sub:
            return set()
        ids = {sub}
        for name, ref in self.principals.items():
            if ref.sub == sub or name == sub:
                ids.add(name)
                ids.update(ref.roles)
        roles = principal.claims.get("roles") or []
        if isinstance(roles, str):
            roles = [roles]
        ids.update(str(r) for r in roles)
        return ids

    def permits(
        self,
        principal: Principal,
        source: str,
        table: str | None = None,
        column: str | None = None,
    ) -> bool:
        ids = {i.lower() for i in self.identities(principal)}
        grants: list[str] = []
        for key, gs in self.grants.items():
            if key.lower() in ids:
                grants.extend(gs)
        return any(_covers(g, source, table, column) for g in grants)
