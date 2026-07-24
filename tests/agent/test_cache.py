import json

import pytest

from datacharter.agent.cache import AnswerCache, contract_fingerprint
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
        yield eng, charter.sources, tmp_path
    finally:
        eng.close()


class _BoomLLM:
    async def stream(self, messages, tools):
        raise AssertionError("LLM must not be called on a cache hit")
        yield  # pragma: no cover


class _ScriptLLM:
    def __init__(self, script):
        self.script = list(script)

    async def stream(self, messages, tools):
        for delta in self.script.pop(0):
            yield delta


def test_cache_get_put_is_normalized(tmp_path):
    cache = AnswerCache(tmp_path / "c.json", "fp1")
    cache.put("How many customers?", "SELECT count(*) FROM customers")
    assert cache.get("  how   many customers ") == "SELECT count(*) FROM customers"


def test_cache_invalidated_on_fingerprint_change(tmp_path):
    path = tmp_path / "c.json"
    AnswerCache(path, "fp1").put("q", "SELECT 1")
    assert AnswerCache(path, "fp2").get("q") is None


async def test_agent_cache_hit_skips_llm(engine):
    eng, sources, ws = engine
    cache = AnswerCache(ws / ".datacharter" / "nl_cache.json", contract_fingerprint(sources))
    cache.put("how many customers", "SELECT count(*) AS n FROM store.customers")
    agent = Agent(ToolBox(eng, sources), AgentConfig(llm=_BoomLLM(), cache=cache))
    events = [e async for e in agent.run("How many customers?")]
    assert events[-1].kind == "done"
    result = next(e for e in events if e.kind == "tool_result")
    assert '"rows": [[3]]' in result.detail  # cached SQL re-ran on current data


async def test_agent_records_query_sql_on_miss(engine):
    eng, sources, ws = engine
    cache = AnswerCache(ws / ".datacharter" / "nl_cache.json", contract_fingerprint(sources))
    sql = "SELECT count(*) AS n FROM store.customers"
    script = [
        [Delta(tool_calls=[ToolCall(id="c1", name="query", arguments=json.dumps({"sql": sql}))])],
        [Delta(text="There are 3 customers.")],
    ]
    agent = Agent(ToolBox(eng, sources), AgentConfig(llm=_ScriptLLM(script), cache=cache))
    [e async for e in agent.run("How many customers?")]
    assert cache.get("how many customers") == sql  # recorded for next time
