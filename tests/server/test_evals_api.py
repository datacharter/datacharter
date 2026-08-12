from fastapi.testclient import TestClient

from datacharter.cli import main as cli_main
from datacharter.server import create_app


def _client(tmp_path, host="127.0.0.1"):
    cli_main(["init", str(tmp_path), "--demo"])
    return TestClient(create_app(tmp_path, host=host), base_url=f"http://{host}")


def test_list_evals_empty(tmp_path):
    with _client(tmp_path) as c:
        assert c.get("/api/evals").json() == {"suites": []}


def test_run_evals_without_llm_returns_actionable_400(tmp_path):
    """No LLM + default backend: the endpoint must 400 with a message the UI can
    show — not a silent empty stream (the "nothing happens" bug)."""
    cli_main(["init", str(tmp_path), "--demo"])
    app = create_app(tmp_path, offline=True)
    with TestClient(app, base_url="http://127.0.0.1") as c:
        r = c.post("/api/evals/run", json={"compare_guides": False, "samples": 1})
    assert r.status_code == 400
    assert r.json()["error"]["type"] == "no_llm"
    assert "Claude Code" in r.json()["error"]["message"]


def test_run_evals_routes_to_claude_code_backend(tmp_path, monkeypatch):
    """When the backend is Claude Code, the eval run drives the CC path (with its
    model defaults) instead of demanding a built-in LLM."""
    import datacharter.agent.eval_runner as er
    from datacharter.agent.eval_runner import RunRecord
    from datacharter.server import agent_backend

    cli_main(["init", str(tmp_path), "--demo"])
    (tmp_path / "evals").mkdir(exist_ok=True)
    (tmp_path / "evals" / "s.yaml").write_text(
        "version: 1\ncases:\n  - question: how many orders?\n"
        "    expect:\n      - { type: answer_contains, value: '90' }\n"
    )
    agent_backend.set_backend(tmp_path, "claude-code")
    app = create_app(tmp_path, offline=True)  # offline ⇒ no built-in LLM at all
    app.state.cc_deny = ["Bash"]  # pretend the sandbox was already asserted

    seen = {}

    async def fake_run_suite_cc(suite, **kw):
        seen.update(kw)
        return RunRecord(suite=suite.name, mode="plain", samples=1,
                         overall={"with_guides": 1.0}, cases=[])

    monkeypatch.setattr(er, "run_suite_cc", fake_run_suite_cc)
    with TestClient(app, base_url="http://127.0.0.1") as c:
        r = c.post("/api/evals/run", json={"compare_guides": False, "samples": 1})
    assert r.status_code == 200
    assert "with_guides" in r.text  # the SSE 'result' frame was emitted
    assert seen["agent_model"] == "sonnet" and seen["judge_model"] == "opus"


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
