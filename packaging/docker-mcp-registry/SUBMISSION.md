# Docker MCP Catalog submission — DataCharter

This directory holds everything needed to list DataCharter in the
[Docker MCP Catalog](https://hub.docker.com/mcp) (which also surfaces in Docker
Desktop's **MCP Toolkit**). Docker builds the image from **our repo-root
`Dockerfile`** at a pinned commit and publishes it as `mcp/datacharter` on
Docker Hub — no image push from us, and the entry runs with **zero config** on
the baked demo dataset (no test-credentials form needed).

## What's here

```
servers/datacharter/
  server.yaml    # catalog entry (metadata, source repo/commit, run config)
  tools.json     # the 6 governed tools + input schemas (generated from mcp/server.py)
```

`tools.json` is regenerated from the live server so it never drifts:

```bash
python - <<'PY'
import json
from datacharter.mcp.server import mcp_tool_defs
tools = [{"name": d["name"], "description": d["description"], "inputSchema": d["inputSchema"]}
         for d in mcp_tool_defs()]
print(json.dumps({"tools": tools}, indent=2))
PY
```

## Local verification (all offline, done before submitting)

1. **Build:** `docker build -t datacharter-mcp .` (from the repo root).
2. **Protocol smoke:** pipe `initialize` → `tools/list` → `tools/call query`
   JSON-RPC lines into `docker run -i --rm datacharter-mcp`; assert the 6 tools
   and demo rows come back.
3. **Conformance:** drive it with the official `mcp` client (dev extra) pointed
   at the container.
4. **Governance proof:** mount a workspace with a PII column
   (`-v "$PWD/examples/ecommerce:/workspace"`), call `query`, assert the masked
   column returns `•••` and `datacharter audit` inside the container shows the
   hash-chained entry.
5. **Zero-network proof:** `docker run --network none -i --rm datacharter-mcp`
   still answers `tools/list`.

## Your submission checklist (needs a GitHub account; no other credentials)

1. **Pin the commit.** In `server.yaml`, set `source.commit` to the SHA of the
   release commit whose `Dockerfile` pins the matching `datacharter==` version
   (currently `0.24.4`). Find it with `git rev-parse v0.24.4`.
2. **Fork & branch.** Fork `docker/mcp-registry` to your personal account;
   branch `add-datacharter`; copy `servers/datacharter/` into the fork.
3. **Validate with their tooling.** In the fork, run their generator/validator
   (`task create -- --category database https://github.com/datacharter/datacharter`
   or `task wizard`), reconcile with the YAML here, then run their local
   build/validate `task`s.
4. **Open the PR.** The template auto-applies. In the description, note:
   zero-config demo mode (no test-credentials form), Apache-2.0 license,
   `Dockerfile` at repo root, and that the server is read-only and PII-masking.
5. **Review.** Every entry is human-reviewed; respond to Docker-team comments.
   On approval it goes live at `hub.docker.com/mcp` and in Docker Desktop's MCP
   Toolkit within ~24h, published as `mcp/datacharter`.
6. **After it lands.** Add the Docker MCP Catalog badge/link to the README and
   datacharter.dev, re-ping IndexNow, and add the catalog URL to the
   external-listings tracker.

## Why DataCharter is differentiated in this catalog

It is the **governed** one: read-only by construction, PII default-masked,
plain-English policies (aggregate-only / k-anonymity), certified metrics, and a
tamper-evident audit trail — all local-first, no accounts, no telemetry.
