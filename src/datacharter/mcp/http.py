"""MCP Streamable HTTP adapter: POST /mcp, JSON-RPC.

Stdio stays the default local transport. Loopback Host is required unless
OAuth is enabled. GET/DELETE are 405; sessions and SSE wait until a tool
needs them.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from datacharter import __version__
from datacharter.mcp.auth import Authenticator, AuthError
from datacharter.mcp.server import handle_message

__all__ = [
    "attach_mcp_routes",
    "create_mcp_http_app",
    "mcp_http_url",
    "mcp_bind_allowed",
]


def mcp_http_url(base: str) -> str:
    """Normalize a serve origin to the Streamable HTTP endpoint."""
    url = base.rstrip("/")
    return url if url.endswith("/mcp") else f"{url}/mcp"


def mcp_bind_allowed(host: str, authenticator: Authenticator) -> bool:
    """Non-loopback bind is allowed only when OAuth is on."""
    from datacharter.mcp.oauth import OAuthVerifier
    from datacharter.server.security import LOOPBACK_HOSTS

    if host.lower() in LOOPBACK_HOSTS:
        return True
    return isinstance(authenticator, OAuthVerifier)


def _loopback_host(request: Request) -> bool:
    from datacharter.server.security import LOOPBACK_HOSTS

    host_name = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]").lower()
    return host_name in LOOPBACK_HOSTS


def _accepts_json(accept: str | None) -> bool:
    if not accept:
        return True
    low = accept.lower()
    return "*/*" in low or "application/json" in low


def _forbidden(kind: str, message: str) -> JSONResponse:
    status = 403 if kind.startswith("forbidden") else 401
    return JSONResponse(status_code=status, content={"error": {"type": kind, "message": message}})


def attach_mcp_routes(app: FastAPI, *, authenticator: Authenticator | None = None) -> None:
    """Mount POST /mcp on an app that already has `app.state.toolbox`."""
    from datacharter.mcp.oauth import OAuthVerifier, authenticator_from_env

    auth = authenticator if authenticator is not None else authenticator_from_env()
    app.state.mcp_auth = auth
    app.state.oauth_config = auth.config if isinstance(auth, OAuthVerifier) else None

    @app.get("/.well-known/oauth-protected-resource")
    async def oauth_protected_resource() -> JSONResponse:
        cfg = app.state.oauth_config
        if cfg is None:
            return JSONResponse(
                status_code=404,
                content={"error": {"type": "not_found", "message": "OAuth is not enabled."}},
            )
        return JSONResponse(
            {
                "resource": cfg.audience,
                "authorization_servers": [cfg.issuer],
                "bearer_methods_supported": ["header"],
            }
        )

    @app.api_route("/mcp", methods=["GET", "DELETE"])
    async def mcp_method_not_allowed() -> JSONResponse:
        return JSONResponse(
            status_code=405,
            headers={"allow": "POST"},
            content={
                "error": {
                    "type": "method_not_allowed",
                    "message": "MCP Streamable HTTP accepts POST.",
                }
            },
        )

    @app.post("/mcp")
    async def mcp_post(request: Request) -> Response:
        if app.state.oauth_config is None and not _loopback_host(request):
            return _forbidden(
                "forbidden_host",
                "MCP Streamable HTTP is loopback-only until OAuth is enabled.",
            )
        from datacharter.server.security import LOOPBACK_HOSTS, origin_allowed

        if not origin_allowed(request, LOOPBACK_HOSTS):
            return _forbidden("forbidden_origin", "Cross-origin request rejected.")
        if not _accepts_json(request.headers.get("accept")):
            return JSONResponse(
                status_code=406,
                content={
                    "error": {
                        "type": "not_acceptable",
                        "message": "Accept application/json.",
                    }
                },
            )
        try:
            principal = await app.state.mcp_auth.authenticate(request)
        except AuthError as exc:
            headers = {}
            if app.state.oauth_config is not None:
                base = str(request.base_url).rstrip("/")
                meta = f"{base}/.well-known/oauth-protected-resource"
                headers["WWW-Authenticate"] = f'Bearer resource_metadata="{meta}"'
            return JSONResponse(
                status_code=exc.status,
                headers=headers,
                content={"error": {"type": "unauthorized", "message": exc.detail}},
            )
        raw = await request.body()
        try:
            message = json.loads(raw.decode() if raw else "null")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JSONResponse(
                status_code=400,
                content={
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"},
                },
            )
        if not isinstance(message, dict):
            return JSONResponse(
                status_code=400,
                content={
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32600, "message": "Invalid Request"},
                },
            )
        from datacharter.audit.sink import bind_principal, reset_principal

        token = bind_principal(principal.subject)
        try:
            toolbox = request.app.state.toolbox
            policy = getattr(request.app.state, "policy", None)
            if policy is not None and principal.subject:
                from datacharter.mcp.governed import GovernedToolBox

                toolbox = GovernedToolBox(toolbox, principal, policy)
            response = await handle_message(message, toolbox)
        finally:
            reset_principal(token)
        if response is None:
            return Response(status_code=202)
        return JSONResponse(content=response)


def create_mcp_http_app(
    workspace: Path | str,
    *,
    authenticator: Authenticator | None = None,
) -> FastAPI:
    """MCP-only ASGI app (no UI) for `datacharter mcp --http`."""
    from datacharter.agent.factory import build_toolbox, detect_auto_pii
    from datacharter.audit import FlightRecorder
    from datacharter.audit.canary import ensure_canaries
    from datacharter.contracts import load_charter
    from datacharter.engine.session import Engine
    from datacharter.engine.statekey import resolve_state_key

    workspace = Path(workspace).resolve()
    loaded = load_charter(workspace)
    state_key = resolve_state_key()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = Engine(workspace, loaded.sources, local_key=state_key).start()
        app.state.engine = engine
        auto_pii = await detect_auto_pii(engine)
        recorder = FlightRecorder(workspace, enabled=loaded.audit_enabled)
        canary = ensure_canaries(workspace, engine, loaded.canary_mode)
        app.state.toolbox = build_toolbox(
            engine, loaded, auto_pii=auto_pii, recorder=recorder, canary=canary
        )
        try:
            yield
        finally:
            engine.close()

    app = FastAPI(title="DataCharter MCP", version=__version__, lifespan=lifespan)
    from datacharter.contracts.grants import policy_from_charter
    from datacharter.server.probes import attach_probes

    app.state.policy = policy_from_charter(loaded)
    attach_mcp_routes(app, authenticator=authenticator)
    attach_probes(app)

    @app.get("/api/health")
    async def health() -> dict:
        return {"status": "ok", "version": __version__, "transport": "mcp-http"}

    return app
