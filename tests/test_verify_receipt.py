"""The standalone, zero-dependency receipt verifier (tools/verify_receipt.py):
its pure-Python Ed25519 must exactly match `cryptography`, and it must agree with
the in-package verifier on real receipts."""

import importlib.util
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from datacharter.provenance import keys, receipt, seal_query

_PATH = Path(__file__).resolve().parent.parent / "tools" / "verify_receipt.py"
_spec = importlib.util.spec_from_file_location("verify_receipt", _PATH)
vr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vr)


def _raw_pub(sk):
    return sk.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def test_ed25519_accepts_valid_and_rejects_tampered():
    for _ in range(50):
        sk = Ed25519PrivateKey.generate()
        pub = _raw_pub(sk)
        msg = os.urandom(1 + os.urandom(1)[0] % 40)
        sig = sk.sign(msg)
        assert vr.ed25519_verify(pub, sig, msg) is True
        bad = bytearray(msg)
        bad[0] ^= 1
        assert vr.ed25519_verify(pub, sig, bytes(bad)) is False
        bsig = bytearray(sig)
        bsig[0] ^= 1
        assert vr.ed25519_verify(pub, bytes(bsig), msg) is False
        assert vr.ed25519_verify(_raw_pub(Ed25519PrivateKey.generate()), sig, msg) is False


def test_ed25519_rejects_malformed_inputs():
    sk = Ed25519PrivateKey.generate()
    assert vr.ed25519_verify(b"short", sk.sign(b"x"), b"x") is False
    assert vr.ed25519_verify(_raw_pub(sk), b"short", b"x") is False


def _workspace(tmp_path):
    (tmp_path / "people.csv").write_text("id,email\n1,a@b.com\n2,c@d.io\n")
    (tmp_path / "charter.yaml").write_text(
        "version: 1\nsources:\n  people:\n    type: csv\n    path: people.csv\n"
        "    pii:\n      people: [email]\n"
    )
    keys.generate(tmp_path)
    return tmp_path


def test_verifies_real_receipt_and_agrees_with_core(tmp_path):
    ws = _workspace(tmp_path)
    r = seal_query(ws, "SELECT id, email FROM people")
    # standalone verifier agrees with the in-package one
    assert vr.verify_receipt(r)["ok"] is True
    assert receipt.verify(r)["ok"] is True
    assert vr.verify_receipt(r, expected_pubkey=r["signature"]["public_key"])["ok"] is True
    assert vr.verify_receipt(r, expected_pubkey="00" * 32)["ok"] is False


def test_standalone_catches_tamper(tmp_path):
    ws = _workspace(tmp_path)
    r = seal_query(ws, "SELECT id, email FROM people")
    r2 = json.loads(json.dumps(r))
    r2["body"]["queries"][0]["row_count"] = 999
    assert vr.verify_receipt(r2)["ok"] is False


def test_cli_exit_codes(tmp_path):
    ws = _workspace(tmp_path)
    r = seal_query(ws, "SELECT id FROM people")
    good = tmp_path / "r.json"
    good.write_text(json.dumps(r))
    assert vr.main([str(good)]) == 0
    r["body"]["principal"] = "tampered"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(r))
    assert vr.main([str(bad)]) == 1
