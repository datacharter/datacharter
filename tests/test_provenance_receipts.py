"""Verifiable answer provenance: keys, receipt integrity/signature, tamper
detection, and an end-to-end governed seal → verify (no LLM, deterministic).

The security claim under test is that a receipt is verifiable offline against a
published key and that any change to the sealed facts is caught."""

import copy

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from datacharter.provenance import keys, receipt, seal_query


def _signer():
    return keys.Signer(Ed25519PrivateKey.generate())


def _body(**over):
    base = dict(
        workspace="w", surface_hash="abc123", principal="u", model="m", question="q",
        queries=[{"sql": "SELECT 1", "relations": ["t"], "masked_columns": ["email"],
                  "row_count": 1, "result_sha256": "x" * 64}],
        answer="ANSWER", audit={"session": "s", "head": "h" * 64, "entries": 1},
        issued_at="2026-01-01T00:00:00.000Z",
    )
    base.update(over)
    return receipt.build_body(**base)


# --- keys -------------------------------------------------------------------

def test_keygen_roundtrip_and_fingerprint(tmp_path):
    s = keys.generate(tmp_path)
    assert len(s.public_hex) == 64 and len(s.key_id) == 16
    assert s.key_id == keys.fingerprint(s.public_raw)
    assert keys.load_signer(tmp_path).public_hex == s.public_hex
    assert keys.load_public(tmp_path) == s.public_raw


def test_keygen_refuses_overwrite_without_force(tmp_path):
    first = keys.generate(tmp_path)
    with pytest.raises(keys.ProvenanceKeyError):
        keys.generate(tmp_path)
    replaced = keys.generate(tmp_path, force=True)
    assert replaced.public_hex != first.public_hex
    assert keys.load_signer(tmp_path).public_hex == replaced.public_hex


def test_load_signer_missing_errors(tmp_path):
    with pytest.raises(keys.ProvenanceKeyError):
        keys.load_signer(tmp_path)


def test_verify_primitive_rejects_wrong_key():
    s, other = _signer(), _signer()
    sig = s.sign(b"data")
    assert keys.verify(s.public_raw, sig, b"data") is True
    assert keys.verify(other.public_raw, sig, b"data") is False
    assert keys.verify(s.public_raw, sig, b"tampered") is False


# --- receipt integrity + signature -----------------------------------------

def test_content_hash_is_order_independent():
    b = _body()
    assert receipt.content_hash(b) == receipt.content_hash(dict(reversed(list(b.items()))))


def test_sign_then_verify_ok():
    s = _signer()
    r = receipt.sign(_body(), s)
    v = receipt.verify(r)
    assert v["ok"] and v["checks"] == {"content_hash": True, "signature": True}
    assert v["public_key"] == s.public_hex and v["key_id"] == s.key_id


def test_pinned_key_match_and_mismatch():
    s = _signer()
    r = receipt.sign(_body(), s)
    assert receipt.verify(r, expected_pubkey=s.public_hex)["ok"] is True
    bad = receipt.verify(r, expected_pubkey="00" * 32)
    assert bad["ok"] is False and bad["checks"]["key_match"] is False


def test_tampered_body_fails_hash_and_signature():
    r = receipt.sign(_body(), _signer())
    r["body"]["queries"][0]["row_count"] = 9999
    v = receipt.verify(r)
    assert v["ok"] is False
    assert v["checks"]["content_hash"] is False and v["checks"]["signature"] is False


def test_tampered_signature_fails_only_signature():
    r = receipt.sign(_body(), _signer())
    sig = r["signature"]["sig"]
    r["signature"]["sig"] = ("A" if sig[0] != "A" else "B") + sig[1:]
    v = receipt.verify(r)
    assert v["checks"]["content_hash"] is True and v["checks"]["signature"] is False


def test_answer_change_breaks_the_seal():
    s = _signer()
    r = receipt.sign(_body(answer="ANSWER"), s)
    forged = receipt.sign(_body(answer="A DIFFERENT ANSWER"), s)
    assert r["body"]["answer_sha256"] != forged["body"]["answer_sha256"]
    # splicing the old signature onto a new answer fails
    spliced = {**forged, "signature": r["signature"], "content_hash": r["content_hash"]}
    assert receipt.verify(spliced)["ok"] is False


# --- end-to-end governed seal ----------------------------------------------

def _workspace(tmp_path):
    (tmp_path / "people.csv").write_text("id,email,name\n1,a@b.com,Ada\n2,c@d.io,Bo\n")
    (tmp_path / "charter.yaml").write_text(
        "version: 1\n"
        "sources:\n"
        "  people:\n"
        "    type: csv\n"
        "    path: people.csv\n"
        "    pii:\n"
        "      people: [email]\n"
    )
    return tmp_path


def test_seal_query_end_to_end(tmp_path):
    ws = _workspace(tmp_path)
    keys.generate(ws)
    r = seal_query(ws, "SELECT id, email FROM people ORDER BY id")
    assert receipt.verify(r)["ok"] is True
    q = r["body"]["queries"][0]
    assert "email" in q["masked_columns"]  # PII masking is sealed into the receipt
    assert q["row_count"] == 2 and "people" in q["relations"]
    assert r["body"]["surface_hash"]  # governance/policy version sealed
    link = receipt.verify_audit_link(r, str(ws))
    assert link["chain_ok"] and link["head_in_chain"]
    tampered = copy.deepcopy(r)
    tampered["body"]["queries"][0]["row_count"] = 999
    assert receipt.verify(tampered)["ok"] is False


def test_seal_refuses_failed_query(tmp_path):
    ws = _workspace(tmp_path)
    keys.generate(ws)
    with pytest.raises(ValueError):
        seal_query(ws, "SELECT * FROM does_not_exist")


def test_seal_answer_window_captures_cross_session_queries(tmp_path):
    """A backend that records its queries under a different session — as Claude
    Code does via /mcp — is still sealed. The turn is a window of the audit log,
    not one session id, and a prior turn's query is excluded."""
    import asyncio
    import json as _json

    from datacharter.agent.factory import build_toolbox, detect_auto_pii
    from datacharter.audit.evidence import read_entries
    from datacharter.audit.recorder import FlightRecorder
    from datacharter.cli import _open_engine
    from datacharter.contracts import load_charter
    from datacharter.provenance import seal_answer

    ws = _workspace(tmp_path)
    keys.generate(ws)
    charter = load_charter(ws)
    engine = _open_engine(ws, charter.sources)
    rec = FlightRecorder(ws, enabled=True)
    try:
        box = build_toolbox(engine, charter, auto_pii=asyncio.run(detect_auto_pii(engine)),
                            recorder=rec)
        rec.start_session("chat", question="old")  # a PRIOR turn — must be excluded
        asyncio.run(box.run("query", _json.dumps({"sql": "SELECT count(*) AS n FROM people"})))
        since = len(read_entries(ws))              # the new turn's window starts here
        turn = rec.start_session("claude-code", question="who are they?")
        rec.start_session("mcp")                   # the out-of-process tool session
        asyncio.run(box.run("query", _json.dumps({"sql": "SELECT id, email FROM people"})))
    finally:
        engine.close()

    r = seal_answer(ws, question="who are they?", answer="Two.", session=turn,
                    since=since, model="claude-code")
    assert receipt.verify(r)["ok"] is True
    q = r["body"]["queries"]
    assert len(q) == 1  # only the turn's query, not the prior turn's count
    assert "SELECT id, email" in q[0]["sql"] and "email" in q[0]["masked_columns"]


def test_seal_answer_seals_a_whole_turn(tmp_path):
    """Simulate an agent turn — a recorded session with two governed queries —
    then seal the NL answer over them."""
    import asyncio
    import json as _json

    from datacharter.agent.factory import build_toolbox, detect_auto_pii
    from datacharter.audit.recorder import FlightRecorder
    from datacharter.cli import _open_engine
    from datacharter.contracts import load_charter
    from datacharter.provenance import seal_answer

    ws = _workspace(tmp_path)
    keys.generate(ws)
    charter = load_charter(ws)
    engine = _open_engine(ws, charter.sources)
    recorder = FlightRecorder(ws, enabled=True)
    try:
        box = build_toolbox(engine, charter, auto_pii=asyncio.run(detect_auto_pii(engine)),
                            recorder=recorder)
        session = recorder.start_session("chat", model="fake", question="who are they?")
        asyncio.run(box.run("query", _json.dumps({"sql": "SELECT id, email FROM people"})))
        asyncio.run(box.run("query", _json.dumps({"sql": "SELECT count(*) AS n FROM people"})))
    finally:
        engine.close()

    r = seal_answer(ws, question="who are they?", answer="Two people; emails masked.",
                    session=session, model="fake")
    assert receipt.verify(r)["ok"] is True
    q = r["body"]["queries"]
    assert len(q) == 2  # both governed queries of the turn are sealed
    assert any("email" in x["masked_columns"] for x in q)
    assert r["body"]["answer_sha256"]  # NL answer sealed
    link = receipt.verify_audit_link(r, str(ws))
    assert link["chain_ok"] and link["head_in_chain"]


def test_cli_keygen_seal_verify(tmp_path):
    from datacharter.cli import main

    ws = _workspace(tmp_path)
    assert main(["provenance", "keygen", str(ws)]) == 0
    out = tmp_path / "receipt.json"
    seal_args = ["provenance", "seal", "SELECT id, email FROM people", str(ws), "-o", str(out)]
    assert main(seal_args) == 0
    assert main(["provenance", "verify", str(out), "--flight", str(ws)]) == 0
    # corrupt the file → verify must fail
    text = out.read_text().replace('"row_count": 2', '"row_count": 42')
    out.write_text(text)
    assert main(["provenance", "verify", str(out)]) == 1
