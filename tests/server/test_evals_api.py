from fastapi.testclient import TestClient

from datacharter.cli import main as cli_main
from datacharter.server import create_app


def _client(tmp_path, host="127.0.0.1"):
    cli_main(["init", str(tmp_path), "--demo"])
    return TestClient(create_app(tmp_path, host=host), base_url=f"http://{host}")


def test_list_evals_empty(tmp_path):
    with _client(tmp_path) as c:
        assert c.get("/api/evals").json() == {"suites": []}


def test_guides_read_write_roundtrip(tmp_path):
    with _client(tmp_path) as c:
        r = c.put("/api/guides", json={"name": "overview", "content": "Use net revenue."})
        assert r.status_code == 200
        body = c.get("/api/guides").json()
        assert any(
            g["name"] == "overview" and "net revenue" in g["content"] for g in body["guides"]
        )


def test_guides_write_refused_off_loopback(tmp_path):
    with _client(tmp_path, host="0.0.0.0") as c:
        r = c.put("/api/guides", json={"name": "x", "content": "y"})
        assert r.status_code == 403


def test_set_table_context_persists(tmp_path):
    with _client(tmp_path) as c:
        r = c.put(
            "/api/guides",
            json={"source": "store", "table": "orders", "context": "one row per order"},
        )
        assert r.status_code == 200
        out = c.post(
            "/api/tool",
            json={"name": "describe_table", "arguments": '{"relation": "store.orders"}'},
        )
        assert "one row per order" in out.text


def test_guide_suggestions_endpoint(tmp_path):
    from datacharter.engine.history import record

    with _client(tmp_path) as c:
        for _ in range(4):
            record(tmp_path, "SELECT 1 FROM sales WHERE refunded = false", 1,
                   {"relations": ["sales"], "columns": [], "lineage": {}})
        body = c.get("/api/guides/suggestions").json()
        assert any("refunded = false" in s["text"] for s in body["suggestions"])
