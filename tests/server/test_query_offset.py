from fastapi.testclient import TestClient

from datacharter.cli import main as cli_main
from datacharter.server import create_app


def test_query_offset_pages_past_row_limit(tmp_path):
    assert cli_main(["init", str(tmp_path), "--demo"]) == 0
    app = create_app(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        first = client.post(
            "/api/query", json={"sql": "SELECT * FROM range(25)", "row_limit": 10}
        )
        assert first.status_code == 200
        body = first.json()
        assert body["truncated"] is True
        assert body["rows"][0] == [0]
        second = client.post(
            "/api/query",
            json={"sql": "SELECT * FROM range(25)", "row_limit": 10, "offset": 10},
        )
        assert second.status_code == 200
        page = second.json()
        assert page["rows"][0] == [10]
        assert page["rows"][-1] == [19]


def test_query_cancel_idle_is_ok(tmp_path):
    assert cli_main(["init", str(tmp_path), "--demo"]) == 0
    app = create_app(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        resp = client.post("/api/query/cancel")
        assert resp.status_code == 200
        assert resp.json()["cancelled"] is True
