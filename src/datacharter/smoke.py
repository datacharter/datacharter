"""A runtime smoke battery: real requests against a running server.

Green unit tests repeatedly failed to catch runtime-only breakage — a frozen
build missing a dynamically-imported dependency (pytz), a wheel missing a
data file — because nothing exercised the *artifact*. This battery runs the
same checks against any served workspace and is used by the desktop app's
`--smoke` (in CI, against the actual dmg/exe) and the release wheel gate.

Each check targets a failure class we have actually shipped:
- timestamptz fetch  → dynamic `pytz` import (broke only in frozen builds)
- upload             → fastapi's lazy `python-multipart` import
- agent-access write → ruamel.yaml (+ its C lib) in the contract writer
- tool masking       → the governed agent surface end to end
- snapshot/recheck   → local DDL write path + persisted snapshot SQL
- audit verify       → flight-recorder chain on this platform's file locking
"""

from __future__ import annotations

__all__ = ["run_battery", "format_results"]


def run_battery(base_url: str) -> list[tuple[str, bool, str]]:
    """Run every check against `base_url`; returns (name, ok, detail) per check.

    Assumes the server is up and serving a workspace with the demo `store`
    source (e.g. `--demo`, or any workspace after POST /api/demo).
    """
    import httpx

    results: list[tuple[str, bool, str]] = []
    client = httpx.Client(base_url=base_url, timeout=30.0)

    def check(name: str, fn) -> None:
        try:
            detail = fn() or "ok"
            results.append((name, True, str(detail)))
        except Exception as exc:  # noqa: BLE001 — every failure is a finding
            results.append((name, False, f"{type(exc).__name__}: {exc}"))

    def health():
        body = client.get("/api/health").raise_for_status().json()
        assert body["status"] == "ok"
        return body["version"]

    def timestamptz():
        body = client.post(
            "/api/query",
            json={"sql": "SELECT TIMESTAMPTZ '2026-01-01 10:00:00+00' AS ts, 42 AS n"},
        ).raise_for_status().json()
        assert body["rows"][0][1] == 42, body
        return f"ts={body['rows'][0][0]}"

    def tables():
        body = client.get("/api/tables").raise_for_status().json()
        names = {t["table"] for t in body["tables"]}
        assert "customers" in names, sorted(names)
        return f"{len(names)} tables"

    def masked_tool():
        import json as _json

        body = client.post(
            "/api/tool",
            json={
                "name": "query",
                "arguments": '{"sql": "SELECT email FROM store.customers LIMIT 1"}',
            },
        ).raise_for_status().json()
        out = body["result"]
        assert "@example.com" not in out, out[:120]
        try:
            masked = _json.loads(out)["rows"][0][0] == "•••"
        except (ValueError, KeyError, IndexError):
            masked = False
        # No substring escape hatch: either the value is structurally masked or
        # the tool refused with an explicit policy error. Anything else fails.
        assert masked or out.startswith("Error: policy"), out[:120]
        return "masked" if masked else "policy-refused"

    def upload():
        resp = client.post(
            "/api/upload",
            files={"file": ("smoke_upload.csv", b"a,b\n1,2\n", "text/csv")},
        ).raise_for_status()
        client.delete("/api/uploads/smoke_upload")
        return f"{resp.status_code}"

    def access_write():
        client.post(
            "/api/agent-access",
            json={"source": "store", "table": "customers", "column": "email", "value": False},
        ).raise_for_status()
        return "contract written"

    def snapshot_recheck():
        client.post(
            "/api/snapshot", json={"name": "smoke_snap", "sql": "SELECT 1 AS x"}
        ).raise_for_status()
        body = client.post("/api/snapshot/smoke_snap/recheck").raise_for_status().json()
        client.delete("/api/snapshot/smoke_snap")
        assert body["changed"] is False, body
        return "recheck unchanged"

    def audit_verify():
        body = client.get("/api/audit/verify").raise_for_status().json()
        assert body["ok"] is True, body
        # The masked-tool check above recorded an access — an empty chain here
        # means the recorder is broken, not that there was nothing to audit.
        assert body["entries"] >= 1, body
        return f"{body['entries']} entries"

    check("health", health)
    check("timestamptz-fetch", timestamptz)
    check("tables", tables)
    check("masked-tool", masked_tool)
    check("upload-multipart", upload)
    check("contract-write", access_write)
    check("snapshot-recheck", snapshot_recheck)
    check("audit-verify", audit_verify)
    client.close()
    return results


def format_results(results: list[tuple[str, bool, str]]) -> str:
    lines = [
        f"  {'✓' if ok else '✗'} {name}: {detail}" for name, ok, detail in results
    ]
    failed = sum(1 for _, ok, _ in results if not ok)
    lines.append(f"smoke battery: {len(results) - failed}/{len(results)} passed")
    return "\n".join(lines)
