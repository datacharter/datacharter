"""Anti-DNS-rebinding / cross-origin request guards (DC-SEC-006).

Pure predicates shared by the core server and any HTTP transport built on the same
governed toolbox: they decide allow/deny from request headers, they do not build
responses. `host_allowed` blocks DNS-rebinding (a bad `Host`); `origin_allowed`
blocks cross-site browser requests (a foreign `Origin` / `Sec-Fetch-Site`).
"""

from __future__ import annotations

from urllib.parse import urlparse

from starlette.requests import Request

__all__ = [
    "LOOPBACK_HOSTS",
    "ALL_INTERFACES",
    "allowed_hosts",
    "host_allowed",
    "origin_allowed",
    "is_request_allowed",
]

# Hostnames that always denote this machine.
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
ALL_INTERFACES = frozenset({"0.0.0.0", "::"})
_CROSS_SITE = frozenset({"cross-site", "cross-origin"})


def allowed_hosts(host: str) -> frozenset[str] | None:
    """Host-header allowlist for a bind address; None = all interfaces (skip)."""
    if host.lower() in ALL_INTERFACES:
        return None  # explicit network opt-in (D4) — a Host allowlist can't apply
    return LOOPBACK_HOSTS | {host.lower()}


def host_allowed(request: Request, allowed: frozenset[str] | None) -> bool:
    """False iff the `Host` header is absent/empty or names a host outside the
    allowlist. Every legitimate HTTP/1.1 client sends Host — an empty one is a
    crafted request and must not slip past the rebinding guard."""
    if allowed is None:
        return True
    host_name = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]").lower()
    return bool(host_name) and host_name in allowed


def origin_allowed(request: Request, allowed: frozenset[str] | None) -> bool:
    """False iff a cross-site `Origin` or `Sec-Fetch-Site` header is present."""
    origin = request.headers.get("origin")
    if origin:
        origin_host = (urlparse(origin).hostname or "").lower()
        if origin_host not in (allowed or LOOPBACK_HOSTS):
            return False
    return (request.headers.get("sec-fetch-site") or "").lower() not in _CROSS_SITE


def is_request_allowed(request: Request, allowed: frozenset[str] | None) -> bool:
    """Both guards — for endpoints (e.g. MCP over HTTP) that want the full check on
    every request, regardless of path."""
    return host_allowed(request, allowed) and origin_allowed(request, allowed)
