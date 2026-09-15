"""Charter Studio: read the contract, patch PII/filters/policies, YAML stays the source of truth."""

from fastapi.testclient import TestClient

from datacharter.contracts import load_charter
from datacharter.server import create_app


def _workspace(tmp_path):
    (tmp_path / "people.csv").write_text("id,email,region\n1,ada@example.com,US\n")
    (tmp_path / "charter.yaml").write_text(
        "version: 1\n"
        "sources:\n"
        "  crm:\n"
        "    type: csv\n"
        "    path: people.csv\n"
        "    pii:\n"
        "      crm: [email]\n"
        "policies:\n"
        "  crm:\n"
        "    - aggregates only\n"
    )
    return tmp_path


def _client(tmp_path):
    app = create_app(_workspace(tmp_path))
    return TestClient(app, base_url="http://127.0.0.1")


def test_get_charter_returns_yaml_and_structured_governance(tmp_path):
    with _client(tmp_path) as client:
        resp = client.get("/api/charter")
        assert resp.status_code == 200
        body = resp.json()
        assert "path: people.csv" in body["yaml"]
        assert "hunter2" not in body["yaml"]
        assert body["sources"][0]["name"] == "crm"
        assert body["sources"][0]["pii"]["crm"] == ["email"]
        assert body["policies"]["crm"] == ["aggregates only"]


def test_studio_patch_replaces_pii_filter_and_policies(tmp_path):
    with _client(tmp_path) as client:
        resp = client.post(
            "/api/charter/studio",
            json={
                "pii": [{"source": "crm", "table": "crm", "columns": ["region"]}],
                "row_filters": [{"source": "crm", "table": "crm", "predicate": "region = 'US'"}],
                "policies": [{"relation": "crm", "sentences": ["no joins"]}],
            },
        )
        assert resp.status_code == 200, resp.text
        charter = load_charter(tmp_path)
        src = charter.sources[0]
        assert list(src.pii["crm"]) == ["region"]
        assert src.row_filters["crm"] == "region = 'US'"
        from datacharter.contracts.policies import render_sentences

        assert render_sentences(charter.policies["crm"]) == ["no joins"]
        yaml_text = (tmp_path / "charter.yaml").read_text()
        assert "email" not in yaml_text.split("pii:")[1].split("policies:")[0]
        got = client.get("/api/charter").json()
        assert got["policies"]["crm"] == ["no joins"]
        assert got["sources"][0]["row_filters"]["crm"] == "region = 'US'"


def test_studio_patch_clears_governance_with_empty_values(tmp_path):
    with _client(tmp_path) as client:
        resp = client.post(
            "/api/charter/studio",
            json={
                "pii": [{"source": "crm", "table": "crm", "columns": []}],
                "policies": [{"relation": "crm", "sentences": []}],
            },
        )
        assert resp.status_code == 200, resp.text
        charter = load_charter(tmp_path)
        assert not charter.sources[0].pii.get("crm")
        assert "crm" not in charter.policies


def test_studio_patch_unknown_source_is_a_write_error(tmp_path):
    with _client(tmp_path) as client:
        resp = client.post(
            "/api/charter/studio",
            json={"pii": [{"source": "ghost", "table": "t", "columns": ["email"]}]},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["type"] == "write_error"


def test_studio_patch_bad_policy_sentence_is_rejected(tmp_path):
    with _client(tmp_path) as client:
        resp = client.post(
            "/api/charter/studio",
            json={"policies": [{"relation": "crm", "sentences": ["do crimes"]}]},
        )
        assert resp.status_code == 400
        assert "unrecognized" in resp.json()["error"]["message"]
