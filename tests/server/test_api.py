import pytest
from fastapi.testclient import TestClient

from datacharter.cli import main as cli_main
from datacharter.server import create_app


@pytest.fixture
def client(tmp_path):
    assert cli_main(["init", str(tmp_path), "--demo"]) == 0
    app = create_app(tmp_path)
    # Loopback Host so the anti-DNS-rebinding allowlist admits the request.
    with TestClient(app, base_url="http://127.0.0.1") as c:
        yield c


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"


def test_sources_no_credentials_leak(client):
    body = client.get("/api/sources").json()
    names = {s["name"] for s in body["sources"]}
    assert names == {"store"}
    assert "credentials" not in str(body)  # has_credential is a bool, not the value
    assert body["sources"][0].keys() == {
        "name",
        "type",
        "path",
        "tables",
        "pii",
        "connection",
        "has_credential",
    }


def test_tables_catalog(client):
    body = client.get("/api/tables").json()
    names = {t["table"] for t in body["tables"]}
    assert {"customers", "orders"} <= names


def test_query_happy_path(client):
    resp = client.post("/api/query", json={"sql": "SELECT count(*) AS n FROM store.customers"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["columns"] == ["n"]
    assert body["rows"] == [[3]]


def test_query_write_rejected_with_envelope(client):
    resp = client.post("/api/query", json={"sql": "DELETE FROM customers"})
    assert resp.status_code == 400
    err = resp.json()["error"]
    assert err["type"] == "query_not_allowed"
    assert "read-only" in err["message"]


def test_query_timeout_envelope(client):
    resp = client.post(
        "/api/query",
        json={"sql": "SELECT count(*) FROM range(1000000000) a, range(1000) b", "timeout_s": 0.3},
    )
    assert resp.status_code == 408
    assert resp.json()["error"]["type"] == "query_timeout"


def test_profile_summarize(client):
    resp = client.post("/api/profile", json={"relation": "store.customers"})
    assert resp.status_code == 200
    assert "column_name" in resp.json()["columns"]


def test_profile_rejects_injection_shape(client):
    resp = client.post("/api/profile", json={"relation": "customers; DROP TABLE x"})
    assert resp.status_code == 422  # pydantic pattern rejects before any SQL


def test_sse_stream_query(client):
    events = []
    with client.stream("GET", "/api/stream/query", params={"sql": "SELECT 1 AS one"}) as resp:
        assert resp.status_code == 200
        for line in resp.iter_lines():
            if line.startswith("event: "):
                events.append(line.removeprefix("event: "))
            if "result" in events:
                break
    assert events[0] == "started"
    assert events[-1] == "result"


def test_sse_stream_error_event(client):
    events = {}
    params = {"sql": "SELECT * FROM nope_missing"}
    with client.stream("GET", "/api/stream/query", params=params) as resp:
        current = None
        for line in resp.iter_lines():
            if line.startswith("event: "):
                current = line.removeprefix("event: ")
            elif line.startswith("data: ") and current:
                events[current] = line.removeprefix("data: ")
                if current in ("result", "error"):
                    break
    assert "error" in events
    assert "nope_missing" in events["error"]


def test_query_files_roundtrip(client):
    resp = client.put("/api/queries", json={"name": "top_orders", "sql": "SELECT 1"})
    assert resp.status_code == 200
    assert client.get("/api/queries").json()["queries"] == ["top_orders"]
    assert client.get("/api/queries/top_orders").json()["sql"] == "SELECT 1"


def test_query_file_traversal_rejected(client):
    resp = client.put("/api/queries", json={"name": "../evil", "sql": "SELECT 1"})
    assert resp.status_code == 422


def test_export_csv(client):
    resp = client.post("/api/export", json={"sql": "SELECT 1 AS a, 'x' AS b", "format": "csv"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert b"a,b" in resp.content


def test_export_rejects_writes(client):
    resp = client.post("/api/export", json={"sql": "DELETE FROM customers", "format": "csv"})
    assert resp.status_code == 400


def test_snapshot_creates_local_table(client):
    resp = client.post("/api/snapshot", json={"sql": "SELECT 7 AS lucky", "name": "mysnap"})
    assert resp.status_code == 200
    q = client.post("/api/query", json={"sql": "SELECT lucky FROM local.mysnap"})
    assert q.json()["rows"] == [[7]]
    tables = client.get("/api/tables").json()["tables"]
    assert any(t["source"] == "local" and t["table"] == "mysnap" for t in tables)


def test_upload_csv_becomes_table(client, tmp_path):
    csv = tmp_path / "My Data-2026.csv"
    csv.write_text("a,b\n1,x\n2,y\n")
    with open(csv, "rb") as fh:
        resp = client.post("/api/upload", files={"file": ("My Data-2026.csv", fh, "text/csv")})
    assert resp.status_code == 200
    table = resp.json()["table"]
    assert table == "my_data_2026"
    q = client.post("/api/query", json={"sql": f"SELECT count(*) FROM {table}"})
    assert q.json()["rows"] == [[2]]


def test_upload_rejects_unknown_type(client):
    resp = client.post("/api/upload", files={"file": ("evil.exe", b"MZ", "application/x-dos")})
    assert resp.status_code == 400


def test_agent_ask_streams_answer(tmp_path):
    from datacharter.agent.llm import Delta
    from datacharter.server import create_app

    class FakeLLM:
        base_url = "http://fake"
        model = "fake-model"

        async def stream(self, messages, tools):
            yield Delta(text="42 orders.")

    cli_main(["init", str(tmp_path), "--demo"])
    app = create_app(tmp_path, llm=FakeLLM())
    ask = {"question": "how many?"}
    with (
        TestClient(app, base_url="http://127.0.0.1") as c,
        c.stream("POST", "/api/agent/ask", json=ask) as resp,
    ):
        assert resp.status_code == 200
        events = [
            ln.removeprefix("event: ") for ln in resp.iter_lines() if ln.startswith("event: ")
        ]
    assert events[0] == "text"
    assert events[-1] == "done"


def test_agent_available_reports_model(client):
    body = client.get("/api/agent/available").json()
    assert "available" in body and "model" in body


# -- DC-SEC-006: DNS-rebinding + CSRF hardening --------------------------------


def test_foreign_host_header_rejected(tmp_path):
    cli_main(["init", str(tmp_path), "--demo"])
    app = create_app(tmp_path)
    with TestClient(app, base_url="http://evil.example.com") as c:
        assert c.get("/api/sources").status_code == 403


def test_cross_origin_request_rejected(client):
    r = client.post(
        "/api/query", json={"sql": "SELECT 1"}, headers={"origin": "http://evil.example.com"}
    )
    assert r.status_code == 403


def test_cross_site_fetch_rejected(client):
    r = client.post(
        "/api/query", json={"sql": "SELECT 1"}, headers={"sec-fetch-site": "cross-site"}
    )
    assert r.status_code == 403


def test_same_origin_allowed(client):
    r = client.post(
        "/api/query",
        json={"sql": "SELECT 1"},
        headers={"origin": "http://127.0.0.1", "sec-fetch-site": "same-origin"},
    )
    assert r.status_code == 200


def test_health_exempt(client):
    assert client.get("/api/health", headers={"sec-fetch-site": "cross-site"}).status_code == 200
