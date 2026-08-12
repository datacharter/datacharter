#!/usr/bin/env python3
"""Standalone verifier for DataCharter answer-provenance receipts.

Zero dependencies — Python 3.8+ standard library only. Copy this one file next to
a receipt and run it; you do not need DataCharter installed. Ed25519 verification
is implemented here (RFC 8032) so the check rests on nothing but the stdlib.

    python3 verify_receipt.py receipt.json
    python3 verify_receipt.py receipt.json --pubkey <hex-you-trust>

Exit code 0 = verified, 1 = not verified. See the receipt format + algorithm at
https://datacharter.dev/provenance.html
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys

# --- Ed25519 (RFC 8032) -----------------------------------------------------
# A compact verify-only implementation over edwards25519, from the RFC 8032
# definitions. Extended coordinates (X, Y, Z, T) keep it to one modular inverse.

_p = 2**255 - 19
_L = 2**252 + 27742317777372353535851937790883648493
_d = (-121665 * pow(121666, _p - 2, _p)) % _p
_I = pow(2, (_p - 1) // 4, _p)  # sqrt(-1)


def _recover_x(y: int, sign: int):
    if y >= _p:
        return None
    x2 = (y * y - 1) * pow(_d * y * y + 1, _p - 2, _p) % _p
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_p + 3) // 8, _p)
    if (x * x - x2) % _p != 0:
        x = x * _I % _p
    if (x * x - x2) % _p != 0:
        return None
    if (x & 1) != sign:
        x = _p - x
    return x


# Base point.
_By = 4 * pow(5, _p - 2, _p) % _p
_Bx = _recover_x(_By, 0)
_B = (_Bx, _By, 1, _Bx * _By % _p)


def _add(P, Q):
    X1, Y1, Z1, T1 = P
    X2, Y2, Z2, T2 = Q
    A = (Y1 - X1) * (Y2 - X2) % _p
    B = (Y1 + X1) * (Y2 + X2) % _p
    C = 2 * T1 * T2 * _d % _p
    D = 2 * Z1 * Z2 % _p
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % _p, G * H % _p, F * G % _p, E * H % _p)


def _scalarmult(P, e: int):
    Q = (0, 1, 1, 0)  # neutral element
    while e > 0:
        if e & 1:
            Q = _add(Q, P)
        P = _add(P, P)
        e >>= 1
    return Q


def _decompress(comp: bytes):
    if len(comp) != 32:
        return None
    y = int.from_bytes(comp, "little")
    sign = (y >> 255) & 1
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, x * y % _p)


def _equal(P, Q) -> bool:
    X1, Y1, Z1, _ = P
    X2, Y2, Z2, _ = Q
    return (X1 * Z2 - X2 * Z1) % _p == 0 and (Y1 * Z2 - Y2 * Z1) % _p == 0


def ed25519_verify(public: bytes, signature: bytes, message: bytes) -> bool:
    """True iff `signature` is a valid Ed25519 signature over `message`."""
    if len(public) != 32 or len(signature) != 64:
        return False
    A = _decompress(public)
    if A is None:
        return False
    R = _decompress(signature[:32])
    if R is None:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= _L:
        return False
    h = int.from_bytes(hashlib.sha512(signature[:32] + public + message).digest(), "little") % _L
    return _equal(_scalarmult(_B, s), _add(R, _scalarmult(A, h)))


# --- receipt verification ---------------------------------------------------

def _canonical(body: dict) -> bytes:
    return json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()


def verify_receipt(receipt: dict, expected_pubkey: str | None = None) -> dict:
    """Return {ok, checks}. Mirrors `datacharter provenance verify`."""
    checks: dict[str, bool] = {}
    body = receipt.get("body")
    sig = receipt.get("signature") or {}
    pub_hex = sig.get("public_key")

    checks["content_hash"] = (
        isinstance(body, dict)
        and hashlib.sha256(_canonical(body)).hexdigest() == receipt.get("content_hash")
    )

    ok_sig = False
    if isinstance(body, dict) and pub_hex and sig.get("sig"):
        try:
            ok_sig = ed25519_verify(
                bytes.fromhex(pub_hex), base64.b64decode(sig["sig"]), _canonical(body)
            )
        except (ValueError, TypeError):
            ok_sig = False
    checks["signature"] = ok_sig

    if expected_pubkey is not None:
        checks["key_match"] = pub_hex == expected_pubkey

    return {"ok": all(checks.values()), "checks": checks}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Verify a DataCharter provenance receipt.")
    ap.add_argument("receipt", help="path to the receipt JSON")
    ap.add_argument("--pubkey", help="pin the expected public key (hex) you trust")
    args = ap.parse_args(argv)

    try:
        with open(args.receipt) as f:
            receipt = json.load(f)
    except (OSError, ValueError) as exc:
        print(f"Could not read receipt: {exc}", file=sys.stderr)
        return 1

    result = verify_receipt(receipt, expected_pubkey=args.pubkey)
    for name, ok in result["checks"].items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    body = receipt.get("body") or {}
    sig = receipt.get("signature") or {}
    print(f"\n  key_id {sig.get('key_id')}  ·  principal {body.get('principal')}"
          f"  ·  {str(body.get('question') or '')[:60]}")
    print("VERIFIED" if result["ok"] else "NOT VERIFIED")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
