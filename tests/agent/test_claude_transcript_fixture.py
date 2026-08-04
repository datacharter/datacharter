"""A REAL Claude Code stream-json transcript, recorded and pinned.

Captured from claude 2.1.221 running a governed data question (list_tables +
query) against a live workspace. parse_stream must keep mapping this exact
stream — the synthetic fixtures previously drifted from reality, and no query
chip ever rendered on real turns because tool inputs live in `assistant`
messages, not the streamed content_block_start.
"""

from pathlib import Path

from datacharter.agent.claude_code import parse_stream

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "claude_stream_real.ndjson"


def _events():
    return list(parse_stream(FIXTURE.read_text().splitlines()))


def test_real_transcript_yields_session_with_governed_tools():
    session = next(e for e in _events() if e["kind"] == "session")
    assert set(session["tools"]) == {
        "mcp__datacharter__query",
        "mcp__datacharter__list_tables",
        "mcp__datacharter__list_sources",
        "mcp__datacharter__describe_table",
    }
    assert session["session_id"]


def test_real_transcript_yields_tool_calls_with_sql():
    calls = [e for e in _events() if e["kind"] == "tool_call"]
    assert [c["tool"] for c in calls] == ["list_tables", "query"]
    assert "SELECT COUNT(*)" in calls[1]["sql"]


def test_real_transcript_yields_text_and_result():
    evs = _events()
    text = "".join(e["text"] for e in evs if e["kind"] == "text")
    assert "3" in text
    result = next(e for e in evs if e["kind"] == "result")
    assert result["is_error"] is False and result["session_id"]


def test_tool_calls_not_duplicated_across_stream_and_assistant_events():
    # Both the legacy stream shape and assistant messages can describe the same
    # tool_use; the id-based dedupe must keep exactly one event per call.
    calls = [e for e in _events() if e["kind"] == "tool_call"]
    assert len(calls) == len({(c["tool"], c["sql"]) for c in calls})
