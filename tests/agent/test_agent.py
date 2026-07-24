import json

import pytest

from datacharter.agent.llm import Delta, ToolCall
from datacharter.agent.loop import Agent, AgentConfig
from datacharter.agent.tools import MASKED, ToolBox
from datacharter.cli import main as cli_main
from datacharter.contracts import load_charter
from datacharter.engine.session import Engine


@pytest.fixture
def engine(tmp_path):
    cli_main(["init", str(tmp_path), "--demo"])
    charter = load_charter(tmp_path)
    eng = Engine(tmp_path, charter.sources).start()
    eng._charter_sources = charter.sources  # noqa: SLF001 - test convenience
    try:
        yield eng, charter.sources
    finally:
        eng.close()


class FakeLLM:
    """Scripted LLM: each item is a list of Delta objects for one stream() call."""

    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.calls = []

    async def stream(self, messages, tools):
        self.calls.append(messages)
        for delta in self.scripted.pop(0):
            yield delta


async def test_toolbox_list_tables_and_query(engine):
    eng, sources = engine
    box = ToolBox(eng, sources)
    tables = json.loads(await box.run("list_tables", "{}"))
    relations = {t["relation"] for t in tables}
    assert {"store.customers", "store.orders"} <= relations

    q = json.dumps({"sql": "SELECT count(*) AS n FROM store.orders"})
    out = json.loads(await box.run("query", q))
    assert out["rows"] == [[90]]


async def test_toolbox_masks_pii(engine):
    eng, sources = engine
    box = ToolBox(eng, sources)
    out = json.loads(
        await box.run("query", json.dumps({"sql": "SELECT email FROM store.customers"}))
    )
    assert out["masked_columns"] == ["email"]
    assert all(row[0] == MASKED for row in out["rows"])


async def test_toolbox_query_write_blocked(engine):
    eng, sources = engine
    box = ToolBox(eng, sources)
    out = await box.run("query", json.dumps({"sql": "DELETE FROM store.customers"}))
    assert out.startswith("Error:")


async def test_describe_rejects_injection(engine):
    eng, sources = engine
    box = ToolBox(eng, sources)
    out = await box.run("describe_table", json.dumps({"relation": "customers; DROP TABLE x"}))
    assert out.startswith("Error:")


async def test_agent_single_answer_no_tools(engine):
    eng, sources = engine
    llm = FakeLLM([[Delta(text="Hello, "), Delta(text="world.")]])
    agent = Agent(ToolBox(eng, sources), AgentConfig(llm=llm))
    kinds = [e.kind async for e in agent.run("hi")]
    assert "text" in kinds
    assert kinds[-1] == "done"


async def test_agent_tool_round_then_answer(engine):
    eng, sources = engine
    scripted = [
        [Delta(tool_calls=[ToolCall(id="c1", name="list_tables", arguments="{}")])],
        [Delta(text="You have customers and orders.")],
    ]
    llm = FakeLLM(scripted)
    agent = Agent(ToolBox(eng, sources), AgentConfig(llm=llm))
    events = [e async for e in agent.run("what tables exist?")]
    kinds = [e.kind for e in events]
    assert "tool_call" in kinds and "tool_result" in kinds
    assert kinds[-1] == "done"
    # The tool result was fed back to the LLM on the second call.
    assert len(llm.calls) == 2
    assert any(m.get("role") == "tool" for m in llm.calls[1])


async def test_agent_reports_llm_error(engine):
    eng, sources = engine

    class BoomLLM:
        async def stream(self, messages, tools):
            from datacharter.agent.llm import LLMError

            raise LLMError("no endpoint")
            yield  # pragma: no cover

    agent = Agent(ToolBox(eng, sources), AgentConfig(llm=BoomLLM()))
    events = [e async for e in agent.run("hi")]
    assert events[-1].kind == "error"
    assert "no endpoint" in events[-1].detail
