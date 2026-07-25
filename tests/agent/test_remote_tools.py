import json

import httpx

from datacharter.agent.remote_tools import RemoteToolBox


async def test_remote_toolbox_forwards_to_api_tool():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"result": "OK"})

    tb = RemoteToolBox("http://serve.local", _transport=httpx.MockTransport(handler))
    out = await tb.run("query", '{"sql":"SELECT 1"}')
    assert out == "OK"
    assert seen["url"] == "http://serve.local/api/tool"
    assert seen["body"] == {"name": "query", "arguments": '{"sql":"SELECT 1"}'}


async def test_remote_toolbox_defaults_empty_arguments():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": json.loads(request.content)["arguments"]})

    tb = RemoteToolBox("http://x", _transport=httpx.MockTransport(handler))
    assert await tb.run("list_tables", "") == "{}"
