"""The chat surface seals each completed answer into a signed provenance receipt
(when a signing key exists) and exposes the verifying public key."""

import json

from fastapi.testclient import TestClient

from datacharter.cli import main as cli_main
from datacharter.provenance import keys, receipt
from datacharter.server import create_app


class ScriptedLLM:
    """Round 1 asks a governed query; round 2 gives the final answer."""

    model = "fake-model"
    base_url = "http://fake"
    api_key = "x"

    def __init__(self):
        from datacharter.agent.llm import Delta, ToolCall

        sql = "SELECT id, email, tier FROM store.customers ORDER BY id LIMIT 3"
        self._scripts = [
            [Delta(tool_calls=[ToolCall(
                id="1", name="query", arguments=json.dumps({"sql": sql}),
            )])],
            [Delta(text="There are 3 customers; emails are masked.")],
        ]
        self._i = 0

    async def stream(self, messages, tools):
        script = self._scripts[min(self._i, len(self._scripts) - 1)]
        self._i += 1
        for d in script:
            yield d


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.split("\n\n"):
        kind = data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                kind = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        if kind is not None:
            events.append((kind, data or {}))
    return events


def _init(tmp_path):
    cli_main(["init", str(tmp_path), "--demo"])


def test_chat_emits_verifiable_receipt(tmp_path):
    _init(tmp_path)
    keys.generate(tmp_path)  # enable signing
    app = create_app(tmp_path, llm=ScriptedLLM())
    with TestClient(app, base_url="http://127.0.0.1") as c:
        r = c.post("/api/agent/ask", json={"question": "how many customers?"})
        assert r.status_code == 200
        events = _parse_sse(r.text)

    receipts = [d["receipt"] for (k, d) in events if k == "receipt"]
    assert len(receipts) == 1
    rec = receipts[0]

    pub = keys.load_public(tmp_path).hex()
    assert receipt.verify(rec, expected_pubkey=pub)["ok"] is True

    body = rec["body"]
    assert body["question"] == "how many customers?"
    assert body["answer_sha256"]  # the NL answer is sealed
    q = body["queries"]
    assert any("email" in x["masked_columns"] for x in q)  # PII masking sealed
    assert any("store.customers" in x["relations"] for x in q)

    link = receipt.verify_audit_link(rec, str(tmp_path))
    assert link["chain_ok"] and link["head_in_chain"]


def test_no_receipt_without_a_key(tmp_path):
    _init(tmp_path)  # no keygen
    app = create_app(tmp_path, llm=ScriptedLLM())
    with TestClient(app, base_url="http://127.0.0.1") as c:
        r = c.post("/api/agent/ask", json={"question": "how many?"})
        events = _parse_sse(r.text)
    assert not any(k == "receipt" for (k, _d) in events)


def test_pubkey_endpoint(tmp_path):
    _init(tmp_path)
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as c:
        assert c.get("/api/provenance/pubkey").json() == {"public_key": None, "key_id": None}
    keys.generate(tmp_path)
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as c:
        got = c.get("/api/provenance/pubkey").json()
    pub = keys.load_public(tmp_path)
    assert got == {"public_key": pub.hex(), "key_id": keys.fingerprint(pub)}
