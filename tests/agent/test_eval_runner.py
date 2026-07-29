import pytest

from datacharter.agent.eval_runner import run_case, run_suite, score_case
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
    answer, sqls, scalar = await run_case(agent, "how many orders?")
    assert "90 orders" in answer
    assert any("store.orders" in s for s in sqls)
    assert scalar == 90


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
