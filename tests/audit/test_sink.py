"""SIEM JSON / OTLP sink: metadata events, never raw rows, off unless env is set."""

import io
import json

from datacharter.audit.recorder import FLIGHT_DIR, FlightRecorder
from datacharter.audit.sink import (
    FanoutSink,
    JsonAuditSink,
    OtlpAuditSink,
    bind_principal,
    reset_principal,
    siem_event,
    sink_from_env,
)


def _rendered(row_count=2, masked=None, relations=None):
    p = {"columns": ["a"], "rows": [[1], [2]], "row_count": row_count, "truncated": False}
    if masked:
        p["masked_columns"] = masked
    if relations:
        p["provenance"] = {"relations": relations}
    return json.dumps(p)


def _entries(ws):
    out = []
    for seg in sorted((ws / FLIGHT_DIR).glob("[0-9]*.jsonl")):
        for line in seg.read_text().splitlines():
            if line.strip():
                out.append(json.loads(line))
    return out


def test_siem_event_allow_has_who_what_not_rows():
    event = siem_event({
        "seq": 2,
        "ts": "2026-09-15T12:00:00+00:00",
        "type": "access",
        "session": "abc",
        "principal": "alice@corp",
        "tool": "query",
        "sql": "SELECT 1 FROM store.orders",
        "relations": ["store.orders"],
        "masked_columns": ["email"],
        "row_count": 2,
        "error": None,
        "result_sha256": "abc",
        "hash": "fff",
        "rows": [[1, "secret@x"]],
    })
    assert event["principal"] == "alice@corp"
    assert event["tool"] == "query"
    assert event["sql"].startswith("SELECT 1")
    assert event["relations"] == ["store.orders"]
    assert event["masked_columns"] == ["email"]
    assert event["row_count"] == 2
    assert event["decision"] == "allow"
    assert "rows" not in event
    assert "secret@x" not in json.dumps(event)


def test_siem_event_not_authorized_is_deny():
    event = siem_event({
        "type": "access",
        "tool": "query",
        "error": "Error: not authorized to query store.customers.",
        "rows": [["leaked"]],
    })
    assert event["decision"] == "deny"
    assert "rows" not in event


def test_json_sink_writes_one_ndjson_line():
    buf = io.StringIO()
    JsonAuditSink(buf).record({"type": "access", "tool": "query", "decision": "allow"})
    lines = [ln for ln in buf.getvalue().splitlines() if ln]
    assert len(lines) == 1
    assert json.loads(lines[0])["tool"] == "query"


def test_sink_from_env_unset_is_none(monkeypatch):
    monkeypatch.delenv("DATACHARTER_AUDIT", raising=False)
    monkeypatch.delenv("DATACHARTER_OTLP_ENDPOINT", raising=False)
    assert sink_from_env() is None


def test_sink_from_env_json_stderr(monkeypatch):
    monkeypatch.setenv("DATACHARTER_AUDIT", "json")
    monkeypatch.delenv("DATACHARTER_OTLP_ENDPOINT", raising=False)
    sink = sink_from_env()
    assert isinstance(sink, JsonAuditSink)


def test_sink_from_env_json_path_appends(tmp_path, monkeypatch):
    dest = tmp_path / "siem.ndjson"
    monkeypatch.setenv("DATACHARTER_AUDIT", f"json:{dest}")
    monkeypatch.delenv("DATACHARTER_OTLP_ENDPOINT", raising=False)
    sink = sink_from_env()
    sink.record({"type": "access", "tool": "query"})
    sink.record({"type": "access", "tool": "list_tables"})
    lines = [json.loads(ln) for ln in dest.read_text().splitlines() if ln]
    assert [e["tool"] for e in lines] == ["query", "list_tables"]


def test_otlp_posts_logs_json_without_rows():
    posted = []

    def _post(url, payload, headers=None):  # noqa: ARG001
        posted.append((url, payload))

    sink = OtlpAuditSink("http://collector.example.test:4318", post=_post)
    event = siem_event({
        "type": "access",
        "tool": "query",
        "sql": "SELECT 1",
        "principal": "alice@corp",
        "error": None,
        "row_count": 1,
        "rows": [[1, "secret"]],
    })
    sink.record(event)
    url, payload = posted[0]
    assert url == "http://collector.example.test:4318/v1/logs"
    blob = json.dumps(payload)
    assert "secret" not in blob
    record = payload["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]
    inner = json.loads(record["body"]["stringValue"])
    assert inner["decision"] == "allow"
    assert inner["principal"] == "alice@corp"
    names = {a["key"]: a["value"]["stringValue"] for a in record["attributes"]}
    assert names["audit.principal"] == "alice@corp"
    assert names["audit.decision"] == "allow"


def test_otlp_endpoint_already_has_logs_path():
    posted = []
    sink = OtlpAuditSink(
        "http://collector.example.test:4318/v1/logs",
        post=lambda url, payload, headers=None: posted.append(url),
    )
    sink.record({"type": "session"})
    assert posted == ["http://collector.example.test:4318/v1/logs"]


def test_sink_from_env_otlp(monkeypatch):
    monkeypatch.delenv("DATACHARTER_AUDIT", raising=False)
    monkeypatch.setenv("DATACHARTER_OTLP_ENDPOINT", "http://collector.example.test:4318")
    sink = sink_from_env()
    assert isinstance(sink, OtlpAuditSink)
    assert sink.url.endswith("/v1/logs")


def test_sink_from_env_json_and_otlp_fanout(monkeypatch):
    monkeypatch.setenv("DATACHARTER_AUDIT", "json")
    monkeypatch.setenv("DATACHARTER_OTLP_ENDPOINT", "http://collector.example.test:4318")
    sink = sink_from_env()
    assert isinstance(sink, FanoutSink)


def test_fanout_keeps_going_if_one_sink_raises():
    kept = []

    class Boom:
        def record(self, event):  # noqa: ARG002
            raise RuntimeError("collector down")

    class Keep:
        def record(self, event):
            kept.append(event)

    FanoutSink([Boom(), Keep()]).record({"type": "access"})
    assert kept == [{"type": "access"}]


def test_recorder_emits_siem_after_chain_write(tmp_path):
    captured = []

    class Rec:
        def record(self, event):
            captured.append(event)

    r = FlightRecorder(tmp_path, sink=Rec())
    r.start_session("mcp")
    r.record_access("query", json.dumps({"sql": "SELECT 1"}), _rendered())
    assert [e["type"] for e in captured] == ["session", "access"]
    assert captured[1]["decision"] == "allow"
    assert captured[1]["sql"] == "SELECT 1"
    assert "rows" not in captured[1]
    from datacharter.audit.evidence import verify_chain

    ok, n, _ = verify_chain(tmp_path)
    assert ok and n == 2


def test_bound_principal_lands_on_chain_and_siem(tmp_path):
    captured = []

    class Rec:
        def record(self, event):
            captured.append(event)

    r = FlightRecorder(tmp_path, sink=Rec())
    token = bind_principal("alice@corp")
    try:
        r.start_session("mcp")
        r.record_access("query", json.dumps({"sql": "SELECT 1"}), _rendered())
    finally:
        reset_principal(token)
    chain = _entries(tmp_path)
    assert chain[0]["principal"] == "alice@corp"
    assert chain[1]["principal"] == "alice@corp"
    assert captured[1]["principal"] == "alice@corp"


def test_sink_failure_does_not_break_chain_or_query(tmp_path):
    class Boom:
        def record(self, event):  # noqa: ARG002
            raise RuntimeError("collector down")

    r = FlightRecorder(tmp_path, sink=Boom())
    r.record_access("query", json.dumps({"sql": "SELECT 1"}), _rendered())
    assert len(_entries(tmp_path)) == 1
    assert r.degraded is False


def test_disabled_recorder_does_not_emit_siem(tmp_path):
    captured = []

    class Rec:
        def record(self, event):
            captured.append(event)

    r = FlightRecorder(tmp_path, enabled=False, sink=Rec())
    r.start_session("mcp")
    r.record_access("query", "{}", _rendered())
    assert captured == []
    assert not (tmp_path / FLIGHT_DIR).exists()
