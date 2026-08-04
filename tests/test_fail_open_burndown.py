"""Every fail-open found in the QA audit, pinned shut.

Each test here encodes an ABSENCE check: the system must refuse, warn, or
degrade loudly where it previously succeeded silently. If one of these starts
failing, something has re-opened a hole that already shipped once.
"""

import asyncio

import pytest

from datacharter.contracts.evals import EvalError, parse_suite
from datacharter.contracts.loader import CharterError, load_charter

BASE = "version: 1\nsources:\n  f:\n    type: csv\n    path: f.csv\n"


@pytest.fixture
def ws(tmp_path):
    (tmp_path / "f.csv").write_text("a,b\n1,2\n")
    return tmp_path


# -- F-1: typo'd top-level governance keys must refuse, not silently disable --

@pytest.mark.parametrize("typo", ["polices", "canry", "audits", "local_acces"])
def test_top_level_typo_refused(ws, typo):
    (ws / "charter.yaml").write_text(BASE + f"{typo}: on\n")
    with pytest.raises(CharterError, match=typo):
        load_charter(ws)


def test_all_real_top_level_keys_still_load(ws):
    (ws / "charter.yaml").write_text(
        BASE + "audit: on\ncanary: off\npolicies: {}\nlocal_access: {}\n"
        "metrics: {}\ntests: {}\n"
    )
    assert load_charter(ws).version == 1


# -- F-8: pii shape — a scalar means one COLUMN, never a character list -------

def test_pii_scalar_means_column(ws):
    (ws / "charter.yaml").write_text(
        "version: 1\nsources:\n  f:\n    type: csv\n    path: f.csv\n"
        "    pii:\n      f: email\n"
    )
    charter = load_charter(ws)
    assert charter.sources[0].pii == {"f": ["email"]}


def test_pii_bad_shape_refused(ws):
    (ws / "charter.yaml").write_text(
        "version: 1\nsources:\n  f:\n    type: csv\n    path: f.csv\n"
        "    pii:\n      f: {email: true}\n"
    )
    with pytest.raises(CharterError, match="pii"):
        load_charter(ws)


# -- F-3: eval cases that cannot fail must refuse to load ---------------------

def test_zero_assertion_case_refused():
    with pytest.raises(EvalError, match="no assertions"):
        parse_suite("s", "cases:\n  - question: anything\n")


def test_typoed_expect_key_refused():
    with pytest.raises(EvalError):
        parse_suite(
            "s",
            "cases:\n  - question: q\n    expects:\n"
            "      - {type: sql_contains, value: x}\n",
        )


# -- F-2: an agent error is an outage, not a scored failure -------------------

def test_eval_error_event_marks_case_errored():
    from datacharter.agent.eval_runner import run_suite
    from datacharter.agent.llm import LLMError
    from datacharter.contracts.evals import EvalSuite

    class DeadLLM:
        async def stream(self, messages, tools):
            raise LLMError("endpoint down")
            yield  # pragma: no cover

    class NullBox:
        guides = ""
        recorder = None
        canary = None

    suite = parse_suite("s", "cases:\n  - question: q\n    expect:\n"
                             "      - {type: sql_contains, value: x}\n")
    assert isinstance(suite, EvalSuite)
    record = asyncio.run(run_suite(suite, NullBox(), llm=DeadLLM()))
    out = record.cases[0].with_guides
    assert out.error is not None and "endpoint down" in out.error
    assert out.passed is False
    assert record.overall["errored"] == 1


# -- F-4: an empty/absent audit chain must never read as verified -------------

def test_verify_chain_empty_is_not_verified(tmp_path):
    from datacharter.audit.evidence import verify_chain

    ok, n, detail = verify_chain(tmp_path)
    assert ok is True and n == 0
    assert "NOTHING VERIFIED" in detail


def test_audit_verify_cli_exit_codes(tmp_path, capsys):
    from datacharter.cli import main as cli_main

    assert cli_main(["init", str(tmp_path)]) == 0
    # no entries yet: exit 2, and never the ✓ success rendering
    assert cli_main(["audit", "verify", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert "NOTHING VERIFIED" in err


# -- F-7: canary plant failure must warn and report planted=False -------------

def test_canary_plant_failure_degrades_loudly(tmp_path, capsys):
    from datacharter.audit.canary import ensure_canaries

    class BrokenEngine:
        def snapshot_sync(self, sql, name):
            raise RuntimeError("disk full")

    guard = ensure_canaries(tmp_path, BrokenEngine(), "block")
    assert guard is not None and guard.planted is False and guard.tokens
    assert "ABSENT" in capsys.readouterr().err


# -- host guard: an empty/missing Host header must not pass -------------------

@pytest.mark.parametrize("headers", [{}, {"host": ""}, {"host": "evil.example"}])
def test_host_guard_fails_closed(headers):
    from starlette.requests import Request

    from datacharter.server.security import allowed_hosts, host_allowed

    scope = {
        "type": "http",
        "headers": [(k.encode(), v.encode()) for k, v in headers.items()],
    }
    assert host_allowed(Request(scope), allowed_hosts("127.0.0.1")) is False


# -- access guard: zero collected relations must not skip the check -----------

def test_access_guard_no_relations_still_blocks_masked_name():
    from datacharter.agent.access_guard import AgentAccessDenied, check_query_access

    with pytest.raises(AgentAccessDenied):
        check_query_access(
            "SELECT * FROM read_csv('x.csv') WHERE email = 'a@b.c'",
            is_masked=lambda s, t, c: False,
            masked_names={"email"},
        )


# -- recorder: append failure warns once instead of dropping writes forever ---

def test_recorder_append_failure_warns(tmp_path, capsys, monkeypatch):
    from datacharter.audit.recorder import FlightRecorder

    rec = FlightRecorder(tmp_path)
    monkeypatch.setattr(rec, "_tail", lambda: (_ for _ in ()).throw(ValueError("corrupt")))
    rec.start_session("test")
    assert "NOT being recorded" in capsys.readouterr().err
    rec.start_session("test")  # second failure: no repeat spam
    assert capsys.readouterr().err == ""


# -- statekey: unencrypted fallback warns ------------------------------------

def test_statekey_fallback_warns(monkeypatch, capsys):
    import keyring

    from datacharter.engine.statekey import resolve_state_key

    monkeypatch.delenv("DATACHARTER_STATE_KEY", raising=False)
    monkeypatch.setattr(
        keyring, "get_password", lambda *a: (_ for _ in ()).throw(RuntimeError("no backend"))
    )
    assert resolve_state_key() is None
    assert "UNENCRYPTED" in capsys.readouterr().err


# -- F-10 + F-6 live through the API ------------------------------------------

@pytest.fixture
def client(tmp_path):
    from fastapi.testclient import TestClient

    from datacharter.cli import main as cli_main
    from datacharter.server import create_app

    assert cli_main(["init", str(tmp_path)]) == 0
    (tmp_path / "p.csv").write_text("a,b\n1,2\n")
    (tmp_path / "charter.yaml").write_text(
        "version: 1\nsources:\n  p:\n    type: csv\n    path: p.csv\n"
    )
    app = create_app(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1") as c:
        yield c


def test_tests_run_zero_tests_is_not_a_pass(client):
    body = client.post("/api/tests/run").json()
    assert body["count"] == 0
    assert body["passed"] is False


def test_audit_verify_api_reports_empty_status(client):
    body = client.get("/api/audit/verify").json()
    assert body["status"] in ("empty", "verified")
    if body["entries"] == 0:
        assert body["status"] == "empty"


def test_masked_output_column_honors_off_override_without_provenance():
    # tools.py name-only fallback previously ignored overrides entirely.
    from datacharter.agent.tools import ToolBox
    from datacharter.models import QueryResult

    box = ToolBox.__new__(ToolBox)
    box._pii = set()
    box._auto_pii = set()
    box._overrides = {"memory": {"columns": {"snap.secret_notes": False}}}
    result = QueryResult(
        columns=["secret_notes"], rows=[["x"]], row_count=1, truncated=False,
        provenance={},
    )
    assert box._mask_indices(result) == {0}


# -- round-2 audit siblings + hardening (0.23.2) --------------------------------

def test_expected_answer_only_eval_is_not_a_free_pass_without_judge():
    # B-7 (F-3 sibling): a case with only expected_answer and no `expect` can be
    # graded ONLY by the judge; without --judge it must be errored, not passed.
    import asyncio

    from datacharter.agent.eval_runner import run_suite
    from datacharter.contracts.evals import EvalCase, EvalSuite

    class ScriptedLLM:
        async def stream(self, messages, tools):
            class D:
                text = "I have no idea."
                tool_calls = None
            yield D()

    class NullBox:
        guides = ""
        recorder = None
        canary = None

    suite = EvalSuite(name="s", cases=[EvalCase(question="q", expected_answer="2")])
    rec = asyncio.run(run_suite(suite, NullBox(), llm=ScriptedLLM()))
    out = rec.cases[0].with_guides
    assert out.passed is False
    assert out.error and "judge" in out.error
    assert rec.overall["with_guides"] == 0.0
    assert rec.overall.get("errored") == 1


def test_audit_verify_reports_broken_on_a_corrupt_line_not_a_crash():
    # B-9: one garbage byte must read as tampering, not a 500/traceback.
    import json as _json
    import tempfile
    from pathlib import Path

    from datacharter.audit.evidence import verify_chain
    from datacharter.audit.recorder import FlightRecorder

    ws = Path(tempfile.mkdtemp())
    rec = FlightRecorder(ws)
    rec.start_session("t")
    rec.record_access("query", _json.dumps({"sql": "SELECT 1"}), "{}")
    seg = next(iter(sorted((ws / ".datacharter" / "flight").glob("[0-9]*.jsonl"))))
    with seg.open("a") as f:
        f.write("{ not json\n")
    ok, n, detail = verify_chain(ws)
    assert ok is False and "BROKEN" in detail


def test_offline_attestation_flags_non_loopback_bind(tmp_path, capsys):
    # B-8: the attestation must not claim "localhost only" on 0.0.0.0.
    import json as _json

    from datacharter.cli import _print_attestation

    _print_attestation(tmp_path, "0.0.0.0", 9000)
    out = capsys.readouterr().out
    assert "localhost only" not in out and "REACHABLE ON THE NETWORK" in out
    record = _json.loads((tmp_path / ".datacharter" / "attestation.json").read_text())
    assert record["loopback_only"] is False

    _print_attestation(tmp_path, "127.0.0.1", 9000)
    assert "localhost only" in capsys.readouterr().out


def test_mutating_source_endpoints_refused_off_loopback(tmp_path):
    # F-J: masking-off and source rewrites must be loopback-only, like guide edits.
    from fastapi.testclient import TestClient

    from datacharter.cli import main as cli_main
    from datacharter.server import create_app

    assert cli_main(["init", str(tmp_path)]) == 0
    app = create_app(tmp_path, host="0.0.0.0")
    with TestClient(app, base_url="http://10.0.0.5") as client:
        r1 = client.post(
            "/api/agent-access",
            json={"source": "local", "table": "t", "column": None, "value": False},
        )
        r2 = client.post("/api/sources", json={"name": "x", "type": "csv", "path": "x.csv"})
        assert r1.status_code == 403 and r2.status_code == 403


def test_mcp_handler_exception_returns_error_frame_not_crash():
    # B-13: a raise inside a handler must become a JSON-RPC error, not kill stdio.
    import asyncio

    from datacharter.mcp.server import handle_message

    class BoomBox:
        guides = ""
        recorder = None

        async def run(self, name, args):
            raise RuntimeError("boom")

    resp = asyncio.run(handle_message(
        {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
         "params": {"name": "query", "arguments": {"sql": "SELECT 1"}}},
        BoomBox(),
    ))
    assert resp["id"] == 7 and resp["error"]["code"] == -32603


def test_canary_token_with_quote_does_not_break_startup(tmp_path, capsys):
    # B-12: tokens come from a user-writable file; a quote must be escaped.
    import json as _json

    from datacharter.audit.canary import CANARY_FILE, ensure_canaries

    path = tmp_path / CANARY_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json.dumps({"tokens": ["ca'nary", "b", "c"]}))

    captured = {}

    class Engine:
        def snapshot_sync(self, sql, name):
            captured["sql"] = sql  # must be valid, no unescaped quote breaking it

    guard = ensure_canaries(tmp_path, Engine(), "block")
    assert guard is not None and guard.planted is True
    assert "ca''nary" in captured["sql"]
