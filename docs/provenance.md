# Verifiable answer provenance

When an AI agent answers a question from your data, the answer is usually just
text — you have to trust that it read the right rows, that PII was masked, and
that nobody edited the result on the way out. DataCharter turns that answer into
something you can **prove**: a signed, portable **receipt** that seals the answer
to the exact governed query, the rows read, the policy version in force, the
model, and the tamper-evident audit chain — and that anyone can verify offline,
without trusting or contacting the operator.

This is the artifact you hand a regulator, an auditor, a board, or a court.

## Try it

```bash
datacharter provenance keygen                 # one signing key per workspace
datacharter provenance pubkey                 # publish this so others can verify

# Seal a governed query into a signed receipt:
datacharter provenance seal "SELECT id, email, tier FROM crm.customers" -o receipt.json

# Verify it offline — recompute the hash, check the signature, pin the key:
datacharter provenance verify receipt.json --pubkey <published-hex> --flight .
```

`seal` runs the query through the **governed surface** — the same path the agent
uses — so masking, policies, and row filters all apply, and the receipt seals the
governed result, never the raw table.

## What a receipt contains

```json
{
  "body": {
    "schema": "datacharter.provenance/v1",
    "issued_at": "2026-08-12T20:00:00.000Z",
    "workspace": "sales",
    "principal": "analyst",
    "model": "claude-...",
    "question": "SELECT id, email, tier FROM crm.customers",
    "surface_hash": "df04...",
    "queries": [
      {
        "sql": "SELECT id, email, tier FROM crm.customers",
        "relations": ["crm.customers"],
        "masked_columns": ["email"],
        "row_count": 3,
        "result_sha256": "0f0a..."
      }
    ],
    "answer_sha256": "0f0a...",
    "audit": { "session": "a482...", "head": "1c0a...", "entries": 2 }
  },
  "content_hash": "0e3b...",
  "signature": {
    "alg": "ed25519",
    "key_id": "b7c6448a1e42da89",
    "public_key": "64ca...",
    "sig": "W/gw..."
  }
}
```

Each sealed field answers a question a reviewer will ask:

| Field | What it proves |
| --- | --- |
| `surface_hash` | The exact governance contract (source/table/column access, declared PII, row filters, policies) in force when the answer was produced. Change the policy, and this changes. |
| `queries[].relations` | Which governed relations the answer actually read. |
| `queries[].masked_columns` | Which columns were masked on the agent's view — proof the PII controls fired. |
| `queries[].result_sha256` | A hash of the exact governed result the surface returned (never the rows themselves). |
| `answer_sha256` | A hash of the answer, binding it to the evidence above. |
| `audit.head` | The head of the append-only, hash-chained audit log at seal time — a Merkle link to the tamper-evident trail. |
| `signature` | An Ed25519 signature over the canonical body. |

The receipt never contains raw rows or PII — only hashes and metadata — so it is
safe to share and can never become a second copy of the data.

## The verification algorithm

A verifier needs only the receipt and the signer's public key (pinned
out-of-band, like an SSH host key). The algorithm is deliberately small so anyone
can re-implement it:

1. **Canonicalize** `body` — serialize as JSON with sorted keys and no
   insignificant whitespace: `separators=(",", ":")`, `sort_keys=true`. Call the
   resulting bytes `C`.
2. **Content hash** — assert `sha256(C)` in hex equals `content_hash`.
3. **Signature** — assert `signature.sig` (base64) is a valid Ed25519 signature
   over `C` for the key `signature.public_key` (32-byte Ed25519 public key, hex).
4. **Key pinning** — assert `signature.public_key` equals the key you trust. The
   `key_id` is `sha256(public_key)[:16]` and is a convenience label only; trust
   the full key.
5. **Audit link (optional)** — given the workspace's audit log, verify the chain
   (`datacharter audit verify`) and confirm `audit.head` appears as some entry's
   hash. This proves the receipt commits to a real point in the tamper-evident
   trail; it is not required for authenticity, which the signature alone
   establishes.

Any change to a sealed fact breaks step 2 and step 3; forging a signature
requires the private key; splicing a valid signature onto different facts fails
step 3. `datacharter provenance verify` performs steps 1–4 always and step 5 with
`--flight`.

## Keys

`datacharter provenance keygen` creates one Ed25519 keypair per workspace under
`.datacharter/keys/` — the private seed (`provenance.key`, written `0600`) signs
receipts; the public key (`provenance.pub`) is what you publish. Protect the
private key: anyone holding it can issue receipts in your name. Rotating the key
(`--force`) invalidates the pinning of every receipt the old key signed, so
publish the new key and keep the old public key available for historical
verification.

## Scope and roadmap

This first version seals a single governed query — the deterministic core of the
mechanism, provable without a model in the loop. Next: sealing an agent's
natural-language answer together with **all** the queries of its turn, and
(enterprise) binding the full principal and delegation chain and an
optionally-TEE-rooted signing key. The receipt schema is versioned
(`datacharter.provenance/v1`) so verifiers can evolve with it.

Next: [Measure agent accuracy — evals →](evals.html)
