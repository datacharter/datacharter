"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from datacharter import __version__
from datacharter.agent import Agent, AgentConfig
from datacharter.agent.cache import AnswerCache, contract_fingerprint
from datacharter.agent.llm import LLMClient
from datacharter.agent.tools import ToolBox
from datacharter.contracts import Charter, CharterError, load_charter
from datacharter.engine.guard import QueryNotAllowed
from datacharter.engine.session import DEFAULT_ROW_LIMIT, Engine, EngineError, QueryTimeout
from datacharter.engine.statekey import resolve_state_key
from datacharter.models import QueryResult, Source, SourceType
from datacharter.server import llm_admin, security, source_admin

HEARTBEAT_S = 1.0
DEFAULT_TIMEOUT_S = 60.0

_MAX_UPLOAD_BYTES = 512 * 1024 * 1024  # 512 MB cap on a single upload


class QueryRequest(BaseModel):
    sql: str
    row_limit: int = Field(default=DEFAULT_ROW_LIMIT, ge=1, le=1_000_000)
    timeout_s: float = Field(default=DEFAULT_TIMEOUT_S, gt=0, le=3600)


class ProfileRequest(BaseModel):
    relation: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_.]*$")


class SaveQueryRequest(BaseModel):
    name: str = Field(pattern=r"^[A-Za-z0-9_][A-Za-z0-9_\-]{0,62}$")
    sql: str


class ExportRequest(BaseModel):
    sql: str
    format: str = Field(pattern=r"^(csv|parquet|json|xlsx)$")


class SnapshotRequest(BaseModel):
    sql: str
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,62}$")


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


_QUERY_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_\-]{0,62}$")


def _error(status: int, kind: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"type": kind, "message": message}})


def create_app(
    workspace: Path | str,
    *,
    charter: Charter | None = None,
    allow_spill: bool = True,
    llm: LLMClient | None = None,
    host: str = "127.0.0.1",
    offline: bool = False,
) -> FastAPI:
    """Build the app for a workspace; charter may be preloaded (demo mode).

    `host` is the intended bind address; it drives the Host-header allowlist that
    blocks DNS-rebinding attacks against the loopback server.
    """
    workspace = Path(workspace).resolve()
    loaded = charter if charter is not None else load_charter(workspace)
    allowed = security.allowed_hosts(host)
    state_key = _state_key()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = Engine(
            workspace, loaded.sources, allow_spill=allow_spill, local_key=state_key
        ).start()
        app.state.engine = engine
        app.state.toolbox = ToolBox(engine, loaded.sources)
        try:
            yield
        finally:
            engine.close()

    app = FastAPI(title="DataCharter", version=__version__, lifespan=lifespan)
    app.state.charter = loaded
    app.state.offline = offline
    # Offline mode: no LLM is ever constructed, so no data can reach a model.
    app.state.llm = None if offline else llm_admin.load_llm(workspace, llm)

    @app.middleware("http")
    async def _origin_guard(request: Request, call_next):
        """Reject DNS-rebinding (bad Host) and cross-site browser requests (CSRF)."""
        if not security.host_allowed(request, allowed):
            return _error(403, "forbidden_host", "Host not allowed.")
        path = request.url.path
        if (
            path.startswith("/api/")
            and path != "/api/health"
            and not security.origin_allowed(request, allowed)
        ):
            return _error(403, "forbidden_origin", "Cross-origin request rejected.")
        return await call_next(request)

    @app.exception_handler(QueryNotAllowed)
    async def _not_allowed(_req: Request, exc: QueryNotAllowed) -> JSONResponse:
        return _error(400, "query_not_allowed", str(exc))

    @app.exception_handler(QueryTimeout)
    async def _timeout(_req: Request, exc: QueryTimeout) -> JSONResponse:
        return _error(408, "query_timeout", str(exc))

    @app.exception_handler(EngineError)
    async def _engine_error(_req: Request, exc: EngineError) -> JSONResponse:
        return _error(400, "engine_error", str(exc))

    @app.exception_handler(CharterError)
    async def _charter_error(_req: Request, exc: CharterError) -> JSONResponse:
        return _error(400, "charter_error", str(exc))

    @app.get("/api/health")
    async def health() -> dict:
        return {"status": "ok", "version": __version__}

    def _refresh_charter() -> None:
        # Re-read the contract so the catalog/PII map reflect a source edit.
        app.state.charter = load_charter(workspace)
        app.state.toolbox = ToolBox(app.state.engine, app.state.charter.sources)

    @app.get("/api/sources")
    async def sources() -> dict:
        # Credentials intentionally omitted — this payload reaches the browser.
        return {
            "warnings": app.state.charter.warnings,
            "sources": [
                {
                    "name": s.name,
                    "type": s.type.value,
                    "path": s.path,
                    "tables": s.tables,
                    "pii": s.pii,
                    "connection": s.connection,
                    "has_credential": bool(s.credentials),
                }
                for s in app.state.charter.sources
            ],
        }

    @app.post("/api/sources")
    async def add_source(form: source_admin.SourceForm) -> dict:
        await asyncio.to_thread(source_admin.create_source, app.state.engine, workspace, form)
        _refresh_charter()
        return {"name": form.name}

    @app.put("/api/sources/{name}")
    async def edit_source(name: str, form: source_admin.SourceForm):
        if name != form.name:
            return _error(400, "name_mismatch", "Source name cannot be changed.")
        if not any(s.name == name for s in app.state.charter.sources):
            return _error(404, "not_found", f"Source '{name}' does not exist.")
        await asyncio.to_thread(source_admin.update_source, app.state.engine, workspace, form)
        _refresh_charter()
        return {"name": name}

    @app.delete("/api/sources/{name}")
    async def remove_source(name: str):
        if not any(s.name == name for s in app.state.charter.sources):
            return _error(404, "not_found", f"Source '{name}' does not exist.")
        await asyncio.to_thread(source_admin.delete_source, app.state.engine, workspace, name)
        _refresh_charter()
        return {"removed": name}

    @app.post("/api/sources/test")
    async def test_source(form: source_admin.SourceForm) -> dict:
        await asyncio.to_thread(source_admin.probe_source, app.state.engine, workspace, form)
        return {"ok": True}

    @app.get("/api/tables")
    async def tables() -> dict:
        result = await app.state.engine.query("SHOW ALL TABLES", timeout_s=30)
        idx = {c: i for i, c in enumerate(result.columns)}
        listing = [
            {
                "source": row[idx["database"]],
                "schema": row[idx["schema"]],
                "table": row[idx["name"]],
                "columns": list(row[idx["column_names"]]),
            }
            for row in result.rows
            if row[idx["database"]] not in ("system", "temp")
        ]
        return {"tables": listing}

    @app.post("/api/query")
    async def query(body: QueryRequest) -> QueryResult:
        return await app.state.engine.query(
            body.sql, timeout_s=body.timeout_s, row_limit=body.row_limit
        )

    @app.post("/api/profile")
    async def profile(body: ProfileRequest) -> QueryResult:
        return await app.state.engine.query(f"SUMMARIZE {body.relation}", timeout_s=120)

    @app.get("/api/queries")
    async def list_queries() -> dict:
        qdir = workspace / "queries"
        files = sorted(p.stem for p in qdir.glob("*.sql")) if qdir.exists() else []
        return {"queries": files}

    @app.get("/api/queries/{name}")
    async def read_query(name: str) -> dict:
        if not _QUERY_NAME.fullmatch(name):
            return _error(400, "bad_name", "Invalid query name.")
        path = workspace / "queries" / f"{name}.sql"
        if not path.exists():
            return _error(404, "not_found", f"queries/{name}.sql does not exist.")
        return {"name": name, "sql": path.read_text()}

    @app.put("/api/queries")
    async def save_query(body: SaveQueryRequest) -> dict:
        qdir = workspace / "queries"
        qdir.mkdir(exist_ok=True)
        (qdir / f"{body.name}.sql").write_text(body.sql)
        return {"saved": body.name}

    @app.post("/api/export")
    async def export(body: ExportRequest) -> FileResponse:
        dest = workspace / ".datacharter" / "tmp" / f"export-{uuid.uuid4().hex[:8]}.{body.format}"
        await asyncio.to_thread(app.state.engine.export_sync, body.sql, body.format, dest)
        media = {
            "csv": "text/csv",
            "json": "application/json",
            "parquet": "application/octet-stream",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }[body.format]
        return FileResponse(
            dest,
            media_type=media,
            filename=f"datacharter-export.{body.format}",
            background=BackgroundTask(lambda: dest.unlink(missing_ok=True)),
        )

    @app.post("/api/snapshot")
    async def snapshot(body: SnapshotRequest) -> dict:
        await asyncio.to_thread(app.state.engine.snapshot_sync, body.sql, body.name)
        return {"snapshot": f"local.{body.name}"}

    @app.post("/api/upload")
    async def upload(file: UploadFile) -> dict:
        suffix = Path(file.filename or "").suffix.lower().lstrip(".")
        types = {"csv": SourceType.CSV, "parquet": SourceType.PARQUET, "json": SourceType.JSON}
        if suffix not in types:
            return _error(
                400, "bad_upload", f"Unsupported file type '.{suffix}'. Use csv, parquet, or json."
            )
        raw_stem = Path(file.filename or "upload").stem.lower()
        stem = re.sub(r"[^a-z0-9_]", "_", raw_stem).strip("_") or "upload"
        if not stem[0].isalpha():
            stem = "t_" + stem
        dest_dir = workspace / ".datacharter" / "uploads"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{stem}.{suffix}"
        size = 0
        with dest.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > _MAX_UPLOAD_BYTES:
                    out.close()
                    dest.unlink(missing_ok=True)
                    return _error(
                        413,
                        "upload_too_large",
                        f"Upload exceeds the {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.",
                    )
                out.write(chunk)
        source = Source(name=stem, type=types[suffix], path=str(dest))
        await asyncio.to_thread(app.state.engine.add_source, source)
        return {"table": stem}

    @app.get("/api/stream/query")
    async def stream_query(
        request: Request, sql: str, timeout_s: float = DEFAULT_TIMEOUT_S
    ) -> StreamingResponse:
        async def events() -> AsyncIterator[str]:
            yield _sse("started", {})
            task = asyncio.create_task(app.state.engine.query(sql, timeout_s=timeout_s))
            try:
                while True:
                    done, _ = await asyncio.wait({task}, timeout=HEARTBEAT_S)
                    if done:
                        break
                    if await request.is_disconnected():
                        task.cancel()
                        return
                    yield _sse("heartbeat", {})
                result: QueryResult = task.result()
                yield _sse("result", result.model_dump())
            except (EngineError, QueryNotAllowed) as exc:
                yield _sse("error", {"type": type(exc).__name__, "message": str(exc)})

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.get("/api/agent/available")
    async def agent_available() -> dict:
        return llm_admin.llm_status(app.state.llm)

    @app.post("/api/agent/config")
    async def agent_config(form: llm_admin.LLMConfigForm):
        if app.state.offline:
            return _error(403, "offline", "Offline mode: connecting an LLM is disabled.")
        llm_admin.save_llm(workspace, form)
        app.state.llm = llm_admin.load_llm(workspace)
        return llm_admin.llm_status(app.state.llm)

    @app.post("/api/agent/ask")
    async def ask(body: AskRequest):
        if app.state.llm is None:
            return _error(400, "no_llm", "No LLM is configured. Connect one to use the chat.")
        cache = AnswerCache(
            workspace / ".datacharter" / "nl_cache.json",
            contract_fingerprint(app.state.charter.sources),
        )
        agent = Agent(app.state.toolbox, AgentConfig(llm=app.state.llm, cache=cache))

        async def events() -> AsyncIterator[str]:
            async for ev in agent.run(body.question):
                yield _sse(ev.kind, {"text": ev.text, "tool": ev.tool, "detail": ev.detail})

        return StreamingResponse(events(), media_type="text/event-stream")

    ui_dist = _ui_dist()
    if ui_dist is not None:
        app.mount("/", StaticFiles(directory=ui_dist, html=True), name="ui")

    return app


def _state_key() -> str | None:
    """Encryption key for the local state DB (D8) — see engine.statekey."""
    return resolve_state_key()


def _ui_dist() -> Path | None:
    """Locate the built UI: packaged static dir first, then the dev build."""
    packaged = Path(__file__).parent / "static"
    if (packaged / "index.html").exists():
        return packaged
    dev = Path(__file__).parents[3] / "ui" / "dist"
    if (dev / "index.html").exists():
        return dev
    return None


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"
