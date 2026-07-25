from datacharter.cli import main
from datacharter.contracts import load_charter
from datacharter.engine.session import Engine


def test_init_scaffolds_workspace_shape(tmp_path):
    assert main(["init", str(tmp_path)]) == 0
    assert (tmp_path / "charter.yaml").exists()
    assert (tmp_path / ".env.example").exists()
    assert (tmp_path / "queries").is_dir()
    gitignore = (tmp_path / ".gitignore").read_text()
    assert ".datacharter/" in gitignore
    assert ".env" in gitignore


def test_init_refuses_overwrite_without_force(tmp_path):
    assert main(["init", str(tmp_path)]) == 0
    assert main(["init", str(tmp_path)]) == 1
    assert main(["init", str(tmp_path), "--force"]) == 0


def test_init_appends_gitignore_preserving_content(tmp_path):
    (tmp_path / ".gitignore").write_text("node_modules/\n")
    main(["init", str(tmp_path)])
    content = (tmp_path / ".gitignore").read_text()
    assert content.startswith("node_modules/")
    assert ".datacharter/" in content


def test_demo_workspace_loads_and_queries_end_to_end(tmp_path):
    assert main(["init", str(tmp_path), "--demo"]) == 0
    charter = load_charter(tmp_path)
    assert {s.name for s in charter.sources} == {"store"}
    assert charter.warnings == []
    with Engine(tmp_path, charter.sources) as eng:
        result = eng.query_sync(
            """
            SELECT c.tier, count(*) AS orders
            FROM store.customers c JOIN store.orders o ON o.customer_id = c.id
            GROUP BY c.tier ORDER BY c.tier
            """
        )
        assert result.columns == ["tier", "orders"]
        assert len(result.rows) == 2


def test_plain_init_charter_loads_as_empty(tmp_path):
    # Regression: plain `init` scaffolds `sources: {}`; the scaffolded charter MUST
    # load. 0.3.1 shipped an init template that `load_charter` then refused.
    assert main(["init", str(tmp_path)]) == 0
    charter = load_charter(tmp_path)
    assert charter.sources == []


def test_plain_init_workspace_serves_end_to_end(tmp_path):
    # The real user path `init` -> `serve`: create_app must boot on a fresh empty
    # workspace and the sources API returns an empty list (sources added later).
    from fastapi.testclient import TestClient

    from datacharter.server import create_app

    assert main(["init", str(tmp_path)]) == 0
    app = create_app(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1") as c:
        resp = c.get("/api/sources")
        assert resp.status_code == 200
        assert resp.json()["sources"] == []


def test_serve_workspace_resolution_prefers_existing_charter(tmp_path):
    from datacharter.cli import _resolve_serve_workspace, main

    main(["init", str(tmp_path)])
    assert _resolve_serve_workspace(str(tmp_path)) == tmp_path.resolve()


def test_serve_workspace_falls_back_to_ephemeral_demo(tmp_path):
    from datacharter.cli import _resolve_serve_workspace
    from datacharter.contracts import load_charter

    ws = _resolve_serve_workspace(str(tmp_path))
    assert ws != tmp_path.resolve()
    assert (ws / "charter.yaml").exists()
    charter = load_charter(ws)
    assert {s.name for s in charter.sources} == {"store"}
