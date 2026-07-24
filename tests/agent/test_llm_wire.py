"""Wire-level: LLMClient against a real OpenAI-protocol socket (not a mock object)."""

import asyncio
import json

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from uvicorn import Config, Server

from datacharter.agent.llm import LLMClient


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


def _make_endpoint() -> FastAPI:
    app = FastAPI()

    @app.post("/v1/chat/completions")
    async def completions(_req: Request) -> StreamingResponse:
        # Emit a text delta, then a two-fragment tool call, then [DONE].
        async def gen():
            yield _sse({"choices": [{"delta": {"content": "Looking… "}}]})
            yield _sse({"choices": [{"delta": {"tool_calls": [
                {"index": 0, "id": "call_1", "function": {"name": "list_tables", "arguments": "{}"}}
            ]}}]})
            yield "data: [DONE]\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    return app


@pytest.fixture
async def endpoint_url():
    config = Config(_make_endpoint(), host="127.0.0.1", port=8766, log_level="error")
    server = Server(config)
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.05)
    try:
        yield "http://127.0.0.1:8766/v1"
    finally:
        server.should_exit = True
        await task


async def test_client_parses_real_sse_stream(endpoint_url):
    client = LLMClient(base_url=endpoint_url, api_key="x", model="test")
    text = ""
    tool_calls = None
    async for delta in client.stream([{"role": "user", "content": "hi"}], []):
        text += delta.text
        if delta.tool_calls:
            tool_calls = delta.tool_calls
    assert text == "Looking… "
    assert tool_calls is not None
    assert tool_calls[0].name == "list_tables"
    assert tool_calls[0].id == "call_1"


async def test_client_reports_http_error():
    from datacharter.agent.llm import LLMError

    client = LLMClient(base_url="http://127.0.0.1:9/v1", api_key="x", model="test")
    with pytest.raises(LLMError):
        async for _ in client.stream([{"role": "user", "content": "hi"}], []):
            pass
