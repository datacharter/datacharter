"""Emit the workspace's governed catalog as an OpenLineage event.

Every governed relation becomes an input `Dataset` on one `COMPLETE` RunEvent: a
`SchemaDatasetFacet` carries its columns and types, and a custom governance facet
records which columns are PII and which are masked on the agent surface, plus the
read-only guarantee. The single event posts to any OpenLineage receiver — Marquez,
DataHub, OpenMetadata — at `<url>/api/v1/lineage`, so a catalog can show not just
what data exists but how DataCharter governs the agent's view of it.

The event is built over the stdlib (`json` + `urllib`); no OpenLineage client
dependency is pulled in.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__all__ = ["build_dataset", "build_run_event", "post_event", "emit"]

PRODUCER = "https://github.com/datacharter/datacharter"
_SCHEMA_FACET_URL = (
    "https://openlineage.io/spec/facets/1-1-1/"
    "SchemaDatasetFacet.json#/$defs/SchemaDatasetFacet"
)
_RUN_EVENT_URL = "https://openlineage.io/spec/2-0-2/OpenLineage.json#/$defs/RunEvent"
_GOVERNANCE_FACET_URL = PRODUCER + "/spec/DataCharterGovernanceFacet.json"


def _now_iso() -> str:
    """OpenLineage wants an ISO-8601 instant with a zone; emit the `...Z` form."""
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def build_dataset(namespace: str, name: str, fields: list[dict]) -> dict:
    """One input Dataset from a relation's resolved columns.

    Each field is `{name, type, pii: bool, masked: bool}`. A masked column is
    annotated in the schema facet and listed in the governance facet, so a reader
    who only understands the standard schema facet still sees the masking note."""
    pii = [f["name"] for f in fields if f.get("pii")]
    masked = [f["name"] for f in fields if f.get("masked")]
    schema_fields = []
    for f in fields:
        field: dict[str, Any] = {"name": f["name"], "type": f["type"]}
        if f.get("masked"):
            field["description"] = "PII — masked on the agent surface"
        schema_fields.append(field)
    return {
        "namespace": namespace,
        "name": name,
        "facets": {
            "schema": {
                "_producer": PRODUCER,
                "_schemaURL": _SCHEMA_FACET_URL,
                "fields": schema_fields,
            },
            "datacharter_governance": {
                "_producer": PRODUCER,
                "_schemaURL": _GOVERNANCE_FACET_URL,
                "readOnly": True,
                "piiColumns": pii,
                "maskedOnAgentSurface": masked,
            },
        },
    }


def build_run_event(
    datasets: list[dict],
    *,
    namespace: str,
    job_name: str,
    run_id: str,
    event_time: str,
) -> dict:
    """A single COMPLETE RunEvent whose inputs are the governed datasets."""
    return {
        "eventType": "COMPLETE",
        "eventTime": event_time,
        "run": {"runId": run_id},
        "job": {"namespace": namespace, "name": job_name},
        "inputs": datasets,
        "outputs": [],
        "producer": PRODUCER,
        "schemaURL": _RUN_EVENT_URL,
    }


def post_event(url: str, event: dict, *, timeout: float = 15.0) -> int:
    """POST one event to `<url>/api/v1/lineage`; return the HTTP status."""
    endpoint = url.rstrip("/") + "/api/v1/lineage"
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(event).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status


async def _collect_relations(box: Any, engine: Any) -> list[dict]:
    """Resolve every governed relation to `{relation, fields[...]}`, reading types
    from DuckDB and the masking decision from the same logic the agent surface uses."""
    relations = json.loads(await box.run("list_tables", "{}"))
    pii_names = box._pii | box._auto_pii
    out = []
    for entry in relations:
        rel = entry["relation"]
        parts = rel.split(".")
        source = parts[-2] if len(parts) >= 2 else ""
        table = parts[-1]
        desc = await engine.query(f"DESCRIBE {rel}", timeout_s=30)
        cidx = desc.columns.index("column_name")
        tidx = desc.columns.index("column_type")
        fields = []
        for row in desc.rows:
            col = str(row[cidx])
            fields.append({
                "name": col,
                "type": str(row[tidx]),
                "pii": col.lower() in pii_names,
                "masked": box._masked(source, table, col),
            })
        out.append({"relation": rel, "fields": fields})
    return out


def emit(
    directory: str,
    url: str | None = None,
    *,
    namespace: str = "datacharter",
    job: str | None = None,
    out: str | None = None,
    event_time: str | None = None,
    run_id: str | None = None,
) -> int:
    """Build the event from the workspace and post it (or write/print it).

    With `url`, POST to the receiver. Else with `out`, write the JSON to a file.
    Else print it to stdout — a dry run you can inspect or pipe."""
    import asyncio
    import uuid

    from datacharter.agent.factory import build_toolbox, detect_auto_pii
    from datacharter.cli import _open_engine
    from datacharter.contracts import load_charter

    ws = Path(directory).resolve()
    if not (ws / "charter.yaml").exists():
        print(f"No charter.yaml in {ws}. Run `datacharter init` first.", file=sys.stderr)
        return 1

    charter = load_charter(ws)
    engine = _open_engine(ws, charter.sources)
    try:
        box = build_toolbox(engine, charter, auto_pii=asyncio.run(detect_auto_pii(engine)))
        relations = asyncio.run(_collect_relations(box, engine))
    finally:
        engine.close()

    datasets = [build_dataset(namespace, r["relation"], r["fields"]) for r in relations]
    event = build_run_event(
        datasets,
        namespace=namespace,
        job_name=job or f"govern.{ws.name}",
        run_id=run_id or str(uuid.uuid4()),
        event_time=event_time or _now_iso(),
    )
    masked_total = sum(len(d["facets"]["datacharter_governance"]["maskedOnAgentSurface"])
                       for d in datasets)

    if not url:
        text = json.dumps(event, indent=2)
        if out:
            Path(out).write_text(text)
            print(f"Wrote {out} — {len(datasets)} dataset(s), {masked_total} masked column(s).")
        else:
            print(text)
        return 0

    try:
        status = post_event(url, event)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")[:300]
        print(f"OpenLineage receiver rejected the event (HTTP {exc.code}): {body}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"Could not reach {url}: {exc.reason}", file=sys.stderr)
        return 1

    print(f"Emitted {len(datasets)} governed dataset(s) to {url} "
          f"(HTTP {status}), job={event['job']['name']}, {masked_total} masked column(s).")
    return 0
