"""OpenLineage emitter: pure event shaping (deterministic) + a full workspace
emit that exercises the engine, masking, and JSON build without a network. The
live post to a real receiver is a marked test, run only when OPENLINEAGE_URL is set.

The RunEvent shape here was verified against a live Marquez (POST → 201, schema
fields and the custom governance facet round-tripped)."""

import json
import os

import pytest

from datacharter import openlineage as ol


def test_build_dataset_facets_and_masking():
    fields = [
        {"name": "id", "type": "BIGINT", "pii": False, "masked": False},
        {"name": "email", "type": "VARCHAR", "pii": True, "masked": True},
    ]
    ds = ol.build_dataset("datacharter", "crm.customers", fields)
    assert ds["namespace"] == "datacharter"
    assert ds["name"] == "crm.customers"
    schema = ds["facets"]["schema"]
    assert schema["_schemaURL"].startswith("https://openlineage.io/spec/facets/")
    assert [f["name"] for f in schema["fields"]] == ["id", "email"]
    # only the masked column carries the annotation
    email = next(f for f in schema["fields"] if f["name"] == "email")
    assert email["description"] == "PII — masked on the agent surface"
    assert "description" not in next(f for f in schema["fields"] if f["name"] == "id")
    gov = ds["facets"]["datacharter_governance"]
    assert gov["readOnly"] is True
    assert gov["piiColumns"] == ["email"]
    assert gov["maskedOnAgentSurface"] == ["email"]


def test_build_dataset_without_pii_is_clean():
    fields = [{"name": "a", "type": "INTEGER", "pii": False, "masked": False}]
    ds = ol.build_dataset("datacharter", "t", fields)
    gov = ds["facets"]["datacharter_governance"]
    assert gov["piiColumns"] == [] and gov["maskedOnAgentSurface"] == []
    assert "description" not in ds["facets"]["schema"]["fields"][0]


def test_build_run_event_shape():
    ev = ol.build_run_event(
        [ol.build_dataset("datacharter", "t", [])],
        namespace="datacharter", job_name="govern.ws",
        run_id="00000000-0000-0000-0000-000000000000", event_time="2026-08-12T00:00:00.000Z",
    )
    assert ev["eventType"] == "COMPLETE"
    assert ev["run"]["runId"] == "00000000-0000-0000-0000-000000000000"
    assert ev["job"] == {"namespace": "datacharter", "name": "govern.ws"}
    assert ev["producer"] == ol.PRODUCER
    assert ev["schemaURL"].endswith("RunEvent")
    assert len(ev["inputs"]) == 1 and ev["outputs"] == []


def test_post_event_targets_lineage_endpoint(monkeypatch):
    seen = {}

    class _Resp:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=15.0):
        seen["url"] = req.full_url
        seen["method"] = req.get_method()
        seen["body"] = json.loads(req.data.decode())
        return _Resp()

    monkeypatch.setattr(ol.urllib.request, "urlopen", fake_urlopen)
    status = ol.post_event("http://marquez:5000/", {"eventType": "COMPLETE"})
    assert status == 201
    assert seen["url"] == "http://marquez:5000/api/v1/lineage"  # trailing slash collapsed
    assert seen["method"] == "POST"
    assert seen["body"]["eventType"] == "COMPLETE"


def _workspace(tmp_path):
    (tmp_path / "people.csv").write_text("id,email,name\n1,ada@example.com,Ada\n2,x@y.io,Bo\n")
    (tmp_path / "charter.yaml").write_text(
        "version: 1\n"
        "sources:\n"
        "  people:\n"
        "    type: csv\n"
        "    path: people.csv\n"
        "    pii:\n"
        "      people: [email]\n"
    )
    return tmp_path


def test_emit_to_file_builds_governed_event(tmp_path):
    """Full path: engine introspection + masking + event build, no network."""
    ws = _workspace(tmp_path)
    out = tmp_path / "event.json"
    rc = ol.emit(str(ws), out=str(out))
    assert rc == 0
    ev = json.loads(out.read_text())
    assert ev["eventType"] == "COMPLETE"
    ds = next(d for d in ev["inputs"] if d["name"] == "people")
    cols = {f["name"] for f in ds["facets"]["schema"]["fields"]}
    assert {"id", "email", "name"} <= cols
    gov = ds["facets"]["datacharter_governance"]
    assert "email" in gov["piiColumns"] and "email" in gov["maskedOnAgentSurface"]
    assert gov["readOnly"] is True


@pytest.mark.skipif(
    not os.environ.get("OPENLINEAGE_URL"),
    reason="set OPENLINEAGE_URL to a running receiver (e.g. Marquez) for the live emit",
)
def test_emit_live_post(tmp_path):
    ws = _workspace(tmp_path)
    assert ol.emit(str(ws), os.environ["OPENLINEAGE_URL"]) == 0
