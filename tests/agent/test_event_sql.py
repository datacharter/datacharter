"""A query tool_call surfaces the executed SQL on the AgentEvent."""

import json

import pytest

from datacharter.agent.llm import Delta, ToolCall
from datacharter.agent.loop import Agent, AgentConfig
from datacharter.agent.tools import ToolBox
from datacharter.cli import main as cli_main
from datacharter.contracts import load_charter
from datacharter.engine.session import Engine


@pytest.fixture
def engine(tmp_path):
    cli_main(["init", str(tmp_path), "--demo"])
    charter = load_charter(tmp_path)
    eng = Engine(tmp_path, charter.sources).start()
    try:
        yield eng, charter.sources
    finally:
        eng.close()


class FakeLLM:
    def __init__(self, scripted):
        self.scripted = list(scripted)

    async def stream(self, messages, tools):
        for delta in self.scripted.pop(0):
            yield delta


async def test_query_tool_call_carries_sql(engine):
    eng, sources = engine
    box = ToolBox(eng, sources)
    sql = "SELECT count(*) AS n FROM store.orders"
    call = ToolCall(id="c1", name="query", arguments=json.dumps({"sql": sql}))
    llm = FakeLLM(
        [
            [Delta(tool_calls=[call])],
            [Delta(text="There are 90 orders.")],
        ]
    )
    events = [e async for e in Agent(box, AgentConfig(llm=llm)).run("how many orders?")]
    calls = [e for e in events if e.kind == "tool_call" and e.tool == "query"]
    assert calls and calls[0].sql == sql
