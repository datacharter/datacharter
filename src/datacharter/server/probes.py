"""Unauthenticated kubelet probes. Host, origin, and OAuth do not apply."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

__all__ = ["PROBE_PATHS", "attach_probes"]

PROBE_PATHS = frozenset({"/health", "/ready"})


def attach_probes(app: FastAPI) -> None:
    """Mount GET /health (liveness) and GET /ready (toolbox is up)."""

    @app.get("/health")
    async def liveness() -> dict:
        return {"status": "ok"}

    @app.get("/ready")
    async def readiness(request: Request) -> JSONResponse:
        if getattr(request.app.state, "toolbox", None) is None:
            return JSONResponse({"status": "not_ready"}, status_code=503)
        return JSONResponse({"status": "ready"})
