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
