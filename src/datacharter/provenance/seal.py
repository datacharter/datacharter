"""Run a query through the governed surface and seal the result into a signed
receipt — the deterministic path that proves the mechanism without an LLM.

The query executes through the same ToolBox the agent uses, so masking, policies,
row filters, and the audit-chain append all happen exactly as they would for a
real answer. The receipt then seals the governed result, not the raw table.
"""

from __future__ import annotations

import asyncio
import getpass
import hashlib
import json
from pathlib import Path

from datacharter.provenance import keys, receipt

__all__ = ["seal_query", "seal_answer"]


def _principal() -> str:
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001
        return "unknown"


def seal_answer(
    workspace: Path | str,
    *,
    question: str,
    answer: str,
    session: str,
    model: str | None = None,
    surface_hash: str | None = None,
    signer: keys.Signer | None = None,
) -> dict:
    """Seal a whole agent turn: the natural-language `answer` plus every governed
    query the turn ran, read straight back from the recorder session so the
    receipt commits to exactly what the audit chain recorded.

    `surface_hash` may be supplied by a caller that already holds the charter;
    otherwise it is computed from the workspace's charter in force."""
    from datacharter.audit.evidence import read_entries
    from datacharter.contracts import load_charter
    from datacharter.contracts.accessplan import effective_surface
    from datacharter.contracts.accessplan import surface_hash as _surface_hash

    ws = Path(workspace).resolve()
    if surface_hash is None:
        surface_hash = _surface_hash(effective_surface(load_charter(ws)))
    signer = signer or keys.load_signer(ws)

    entries = [e for e in read_entries(ws) if e.get("session") == session]
    queries = [
        {
            "sql": e.get("sql"),
            "relations": e.get("relations") or [],
            "masked_columns": e.get("masked_columns") or [],
            "row_count": e.get("row_count"),
            "result_sha256": e.get("result_sha256"),
        }
        for e in entries
        if e.get("type") == "access" and e.get("sql")
    ]
    audit = (
        {"session": session, "head": entries[-1]["hash"], "entries": len(entries)}
        if entries
        else None
    )
    body = receipt.build_body(
        workspace=ws.name,
        surface_hash=surface_hash,
        principal=_principal(),
        model=model,
        question=question,
        queries=queries,
        answer=answer,
        audit=audit,
    )
    return receipt.sign(body, signer)


def seal_query(
    workspace: Path | str,
    sql: str,
    *,
    model: str | None = None,
    signer: keys.Signer | None = None,
) -> dict:
    """Execute `sql` through the governed surface and return a signed receipt."""
    from datacharter.agent.factory import build_toolbox, detect_auto_pii
    from datacharter.audit.evidence import read_entries
    from datacharter.audit.recorder import FlightRecorder
    from datacharter.cli import _open_engine
    from datacharter.contracts import load_charter
    from datacharter.contracts.accessplan import effective_surface, surface_hash

    ws = Path(workspace).resolve()
    charter = load_charter(ws)
    s_hash = surface_hash(effective_surface(charter))
    signer = signer or keys.load_signer(ws)

    engine = _open_engine(ws, charter.sources)
    recorder = FlightRecorder(ws, enabled=True)
    try:
        auto_pii = asyncio.run(detect_auto_pii(engine))
        box = build_toolbox(engine, charter, auto_pii=auto_pii, recorder=recorder)
        session = recorder.start_session(s_hash, model=model, question=sql)
        out = asyncio.run(box.run("query", json.dumps({"sql": sql})))
    finally:
        engine.close()

    if out.startswith("Error:"):
        raise ValueError(f"refusing to seal a failed query: {out}")

    parsed = json.loads(out)
    prov = parsed.get("provenance") or {}
    query_rec = {
        "sql": sql,
        "relations": list(prov.get("relations") or []),
        "masked_columns": parsed.get("masked_columns") or [],
        "row_count": parsed.get("row_count"),
        # the same hash the audit recorder stores: SHA-256 of the exact governed
        # result string the surface returned.
        "result_sha256": hashlib.sha256(out.encode()).hexdigest(),
    }

    entries = [e for e in read_entries(ws) if e.get("session") == session]
    audit = (
        {"session": session, "head": entries[-1]["hash"], "entries": len(entries)}
        if entries
        else None
    )

    body = receipt.build_body(
        workspace=ws.name,
        surface_hash=s_hash,
        principal=_principal(),
        model=model,
        question=sql,
        queries=[query_rec],
        answer=out,
        audit=audit,
    )
    return receipt.sign(body, signer)
