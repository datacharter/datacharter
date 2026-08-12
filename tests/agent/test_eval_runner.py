import pytest

from datacharter.agent.eval_runner import (
    run_case,
    run_case_cc,
    run_suite,
    run_suite_cc,
    score_case,
)
from datacharter.agent.llm import Delta, ToolCall
from datacharter.agent.loop import Agent, AgentConfig
from datacharter.agent.tools import ToolBox
from datacharter.cli import main as cli_main
from datacharter.contracts import load_charter
from datacharter.contracts.evals import EvalAssertion, EvalCase, EvalSuite
from datacharter.engine.session import Engine


class ScriptedLLM:
    """Replays scripted Delta lists; one list per stream() call."""

    def __init__(self, script):
        self.script = list(script)

    async def stream(self, messages, tools):
        for d in self.script.pop(0):
            yield d


def _query_then_answer(sql, answer):
    return [
        [Delta(tool_calls=[ToolCall(id="1", name="query", arguments=f'{{"sql": "{sql}"}}')])],
        [Delta(text=answer)],
    ]


@pytest.fixture
def demo(tmp_path):
    cli_main(["init", str(tmp_path), "--demo"])
    charter = load_charter(tmp_path)
    eng = Engine(tmp_path, charter.sources).start()
    try:
        yield eng, charter.sources
    finally:
        eng.close()


async def test_run_case_captures_answer_sql_and_scalar(demo):
    eng, sources = demo
    box = ToolBox(eng, sources)
    llm = ScriptedLLM(
        _query_then_answer("SELECT count(*) AS n FROM store.orders", "There are 90 orders.")
    )
    agent = Agent(box, AgentConfig(llm=llm))
    answer, sqls, scalar, error = await run_case(agent, "how many orders?")
    assert "90 orders" in answer
    assert any("store.orders" in s for s in sqls)
    assert scalar == 90
    assert error is None


def test_score_case_all_assertions_pass():
    case = EvalCase(
        question="q",
        expect=[
            EvalAssertion(type="sql_contains", value="orders"),
            EvalAssertion(type="answer_contains", value="90"),
        ],
    )
    outcome = score_case(
        case, answer="There are 90 orders.", sqls=["SELECT * FROM store.orders"], scalar=90
    )
    assert outcome.passed is True
    assert [a.passed for a in outcome.assertions] == [True, True]


def test_score_case_fails_when_one_assertion_fails():
    case = EvalCase(question="q", expect=[EvalAssertion(type="answer_contains", value="zzz")])
    outcome = score_case(case, answer="nope", sqls=[], scalar=None)
    assert outcome.passed is False


async def test_run_suite_guide_lift(demo):
    eng, sources = demo
    box_on = ToolBox(eng, sources, guides="Count from store.orders.")
    box_off = ToolBox(eng, sources, guides="")
    suite = EvalSuite(
        name="s",
        cases=[
            EvalCase(
                question="how many orders?",
                expect=[EvalAssertion(type="answer_contains", value="90")],
            )
        ],
    )

    class TwoRunLLM:
        def __init__(self):
            self.script = _query_then_answer(
                "SELECT count(*) AS n FROM store.orders", "90 orders"
            ) + [[Delta(text="I am not sure.")]]

        async def stream(self, messages, tools):
            for d in self.script.pop(0):
                yield d

    record = await run_suite(suite, box_on, llm=TwoRunLLM(), toolbox_off=box_off, samples=1)
    assert record.mode == "compare-guides"
    assert record.overall["with_guides"] == 1.0
    assert record.overall["without_guides"] == 0.0
    assert record.overall["lift"] == 1.0
    assert record.cases[0].without_guides is not None


class DirectAnswerLLM:
    """Agent answers directly (1 round, no tools), then serves scripted judge verdicts."""

    def __init__(self, answer, judge_verdicts):
        self.answer = answer
        self.judge_verdicts = list(judge_verdicts)
        self.calls = 0

    async def stream(self, messages, tools):
        self.calls += 1
        # A judge call has no tools and a grading system prompt; agent calls pass TOOL_SPECS.
        is_judge = not tools
        if is_judge:
            yield Delta(text=self.judge_verdicts.pop(0))
        else:
            yield Delta(text=self.answer)


async def test_judge_pass_makes_case_pass(demo):
    eng, sources = demo
    box = ToolBox(eng, sources)
    suite = EvalSuite(
        name="s",
        cases=[
            EvalCase(
                question="how many orders?",
                expect=[EvalAssertion(type="answer_contains", value="90")],
                expected_answer="There are 90 orders.",
            )
        ],
    )
    rec = await run_suite(
        suite, box, llm=DirectAnswerLLM("There are 90 orders.", ["PASS"]), samples=1, judge=True
    )
    out = rec.cases[0].with_guides
    assert out.passed is True
    assert any(a.type == "judge" and a.passed for a in out.assertions)


async def test_judge_fail_fails_case_even_if_assertions_pass(demo):
    eng, sources = demo
    box = ToolBox(eng, sources)
    suite = EvalSuite(
        name="s",
        cases=[
            EvalCase(
                question="how many orders?",
                expect=[EvalAssertion(type="answer_contains", value="90")],
                expected_answer="Exactly 90 orders, none refunded.",
            )
        ],
    )
    rec = await run_suite(
        suite, box, llm=DirectAnswerLLM("There are 90 orders.", ["FAIL"]), samples=1, judge=True
    )
    out = rec.cases[0].with_guides
    assert out.passed is False
    assert any(a.type == "judge" and not a.passed for a in out.assertions)


async def test_judge_skipped_without_expected_answer(demo):
    eng, sources = demo
    box = ToolBox(eng, sources)
    suite = EvalSuite(
        name="s",
        cases=[
            EvalCase(
                question="how many orders?",
                expect=[EvalAssertion(type="answer_contains", value="90")],
            )
        ],
    )
    # No judge verdicts scripted; if the judge were called it'd IndexError.
    rec = await run_suite(
        suite, box, llm=DirectAnswerLLM("There are 90 orders.", []), samples=1, judge=True
    )
    out = rec.cases[0].with_guides
    assert out.passed is True
    assert not any(a.type == "judge" for a in out.assertions)


# --- Claude Code backend -----------------------------------------------------
# The subprocess boundary (`run_turn`/`grade`) is mocked: a nested `claude`
# refuses to launch inside a Claude Code session, so these fakes stand in for it.


def _fake_run_turn(events_for):
    """Build a `run_turn` stand-in. `events_for(context) -> list[event]` lets a
    test vary the stream by whether the guides are present in the system prompt."""

    async def fake(question, serve_url, session_id=None, deny=None,
                   context=None, model=None, **_kw):
        for ev in events_for(context):
            yield ev

    return fake


async def test_run_case_cc_captures_answer_and_sql(monkeypatch):
    events = [
        {"kind": "tool_call", "tool": "query", "sql": "SELECT count(*) FROM store.orders"},
        {"kind": "text", "text": "There are 90 orders."},
        {"kind": "result", "session_id": "s1", "text": "There are 90 orders.", "is_error": False},
    ]
    monkeypatch.setattr(
        "datacharter.agent.claude_code.run_turn", _fake_run_turn(lambda _c: events)
    )
    answer, sqls, scalar, error = await run_case_cc(
        "how many orders?", "http://x", deny=None, guides="G", with_guides=True, model="sonnet"
    )
    assert answer == "There are 90 orders."
    assert sqls == ["SELECT count(*) FROM store.orders"]
    assert scalar is None  # CC surfaces no result rows
    assert error is None


async def test_run_case_cc_answer_from_result_when_no_text_deltas(monkeypatch):
    events = [{"kind": "result", "session_id": "s1", "text": "42 orders.", "is_error": False}]
    monkeypatch.setattr(
        "datacharter.agent.claude_code.run_turn", _fake_run_turn(lambda _c: events)
    )
    answer, _sqls, _scalar, error = await run_case_cc(
        "q", "http://x", deny=None, guides=None, with_guides=False, model="sonnet"
    )
    assert answer == "42 orders."
    assert error is None


async def test_run_case_cc_surfaces_error_event(monkeypatch):
    events = [{"kind": "error", "detail": "Claude Code exited with code 1."}]
    monkeypatch.setattr(
        "datacharter.agent.claude_code.run_turn", _fake_run_turn(lambda _c: events)
    )
    answer, _sqls, _scalar, error = await run_case_cc(
        "q", "http://x", deny=None, guides=None, with_guides=True, model="sonnet"
    )
    assert answer == ""
    assert error == "Claude Code exited with code 1."


async def test_run_suite_cc_guide_lift(monkeypatch):
    # With guides the agent answers "90"; without them it doesn't — a real lift.
    def events_for(context):
        good = context is not None and "# Workspace guides" in context
        text = "90 orders" if good else "I am not sure."
        return [{"kind": "result", "session_id": "s", "text": text, "is_error": False}]

    monkeypatch.setattr(
        "datacharter.agent.claude_code.run_turn", _fake_run_turn(events_for)
    )
    suite = EvalSuite(
        name="s",
        cases=[EvalCase(
            question="how many orders?",
            expect=[EvalAssertion(type="answer_contains", value="90")],
        )],
    )
    rec = await run_suite_cc(
        suite, serve_url="http://x", deny=None, guides="Count from store.orders.",
        compare=True, samples=1, agent_model="sonnet",
    )
    assert rec.mode == "compare-guides"
    assert rec.overall["with_guides"] == 1.0
    assert rec.overall["without_guides"] == 0.0
    assert rec.overall["lift"] == 1.0


async def test_run_suite_cc_result_scalar_is_errored_not_failed(monkeypatch):
    # The CC backend surfaces no result rows; a result_scalar case must be reported
    # as unscorable (errored), never a misleading ✗ on a possibly-correct answer.
    called = {"n": 0}

    async def boom(*a, **k):
        called["n"] += 1
        yield {"kind": "result", "text": "42", "is_error": False}

    monkeypatch.setattr("datacharter.agent.claude_code.run_turn", boom)
    suite = EvalSuite(
        name="s",
        cases=[EvalCase(
            question="how many orders?",
            expect=[EvalAssertion(type="result_scalar", equals=90)],
        )],
    )
    rec = await run_suite_cc(
        suite, serve_url="http://x", deny=None, guides="G", agent_model="sonnet"
    )
    out = rec.cases[0].with_guides
    assert out.passed is False
    assert out.error is not None and "result_scalar" in out.error
    assert rec.overall.get("errored") == 1
    assert called["n"] == 0  # the agent run was skipped — no wasted claude turn


async def test_run_suite_cc_judge_uses_separate_model(monkeypatch):
    events = [{"kind": "result", "session_id": "s", "text": "There are 90 orders.",
               "is_error": False}]
    monkeypatch.setattr(
        "datacharter.agent.claude_code.run_turn", _fake_run_turn(lambda _c: events)
    )
    seen = {}

    async def fake_grade(prompt, model=None, system=None):
        seen["model"] = model
        return "PASS"

    monkeypatch.setattr("datacharter.agent.claude_code.grade", fake_grade)
    suite = EvalSuite(
        name="s",
        cases=[EvalCase(
            question="how many orders?",
            expect=[EvalAssertion(type="answer_contains", value="90")],
            expected_answer="There are 90 orders.",
        )],
    )
    rec = await run_suite_cc(
        suite, serve_url="http://x", deny=None, guides="G", judge=True,
        agent_model="sonnet", judge_model="opus",
    )
    out = rec.cases[0].with_guides
    assert out.passed is True
    assert any(a.type == "judge" and a.passed for a in out.assertions)
    assert seen["model"] == "opus"  # judge ran on the distinct, stronger model
