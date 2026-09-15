---
layout: default
title: MCP server — connect Claude, Cursor, or Cline to your data, governed
description: Expose your workspace to any MCP client — read-only, PII-masked SQL over your files and databases, with per-column access from your data contract.
---

MCP — the [Model Context Protocol](https://modelcontextprotocol.io) — is the
open standard AI apps like Claude, Cursor, and Cline use to call external
tools. `datacharter mcp` runs an MCP server that exposes your workspace's data
to any such client — **safely**. The same governance the built-in agent uses is
applied to every tool call:

- **Read-only** — writes and filesystem/remote functions are rejected by the
  SQL parser guard, regardless of the query the client sends.
- **PII-masked** — PII columns, whether declared in `charter.yaml` or
  auto-detected, are masked in results so the model never sees the raw values; the
  same [`agent_access`](charter-yaml.html#agent_access) overrides apply here too.
- **Credential-scrubbed** — connection secrets never appear in errors.

Want to see exactly what a client receives before wiring one up? Open the UI
(`datacharter serve`) and flip **Agent view** on any result — PII columns render
as `•••`, which is precisely what `query` returns over MCP.

## Run it

```sh
datacharter mcp            # stdio (default). Claude Desktop, Cursor, Cline.
datacharter mcp /path/to/workspace
datacharter serve          # also serves MCP Streamable HTTP at /mcp
datacharter mcp --http     # MCP-only HTTP on http://127.0.0.1:8765/mcp
```

**stdio** speaks JSON-RPC 2.0 on standard input/output. Diagnostics go to
standard error. A charter is required (`datacharter init` first).

**`--guard COMMAND`** sits in front of someone else's MCP server. DataCharter
spawns that command, relays JSON-RPC, and on every `tools/call` result:
heuristic email/SSN redaction (not charter-grade column masking), canary
scan if the workspace has tokens, a size cap, and a flight-recorder entry.
Upstream tool names pass through. Cannot combine with `--http` or
`--serve-url`.

```sh
datacharter mcp --guard "npx -y some-mcp-server"
```

**Streamable HTTP** is the same governed tools on `POST /mcp`, bound to
loopback. `datacharter serve` mounts it next to the UI so one process holds
one engine. `datacharter mcp --http` is the MCP-only server (default port
8765). Non-loopback binds are refused unless OAuth is enabled.

DataCharter is published in the official
[MCP Registry](https://registry.modelcontextprotocol.io) as
`io.github.datacharter/datacharter`, so MCP clients that read the registry can
discover it directly. It is also listed on
[Glama](https://glama.ai/mcp/servers/datacharter/datacharter):

[![DataCharter MCP server on Glama](https://glama.ai/mcp/servers/datacharter/datacharter/badges/score.svg)](https://glama.ai/mcp/servers/datacharter/datacharter)

Workspace [guides](charter-yaml.html#context-and-guides-agent-context) ride the
protocol's `initialize` `instructions` field, so clients inject your data
owners' context into the model automatically; `describe_table` includes a
`context` key for tables with declared context.

## Tools exposed

| Tool | Arguments | Returns |
| --- | --- | --- |
| `list_sources` | — | configured sources and their types |
| `list_tables` | — | queryable relations with column names |
| `describe_table` | `relation` | columns and types for one relation |
| `query` | `sql` | rows from a read-only SQL query (PII masked) |
| `list_metrics` | — | certified metrics: name, expression, dimensions, time support |
| `query_metric` | `name`, `by?`, `grain?` | a certified metric's governed result |

Certified metrics are defined once in `charter.yaml` under
[`metrics:`](charter-yaml.html#metrics); `query_metric` resolves a metric to a
single governed SELECT and runs it through the same `query` chokepoint, so
masking, row filters, and policies all apply.

## Wire it into an MCP client

Most clients take a JSON config that launches the server as a subprocess. For
example:

```json
{
  "mcpServers": {
    "datacharter": {
      "command": "datacharter",
      "args": ["mcp", "/path/to/your/workspace"]
    }
  }
}
```

HTTP (after `datacharter serve`, or `datacharter mcp --http`):

```json
{
  "mcpServers": {
    "datacharter": {
      "type": "http",
      "url": "http://127.0.0.1:8321/mcp"
    }
  }
}
```

`datacharter connect --serve-url http://127.0.0.1:8321` prints that block with
`/mcp` already on the URL. Claude Code:

```sh
claude mcp add --transport http datacharter http://127.0.0.1:8321/mcp
```

Use the absolute path to your workspace (the directory containing
`charter.yaml`). If `datacharter` is installed in a virtual environment, use its
full path (or `uvx datacharter`).

Where that JSON goes, per client:

- **Claude Desktop** — Settings → Developer → Edit Config, or edit
  `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) /
  `%APPDATA%\Claude\claude_desktop_config.json` (Windows), then restart the app.
- **Claude Code** — `claude mcp add datacharter -- datacharter mcp /path/to/workspace`,
  or add the block to `.mcp.json` in your project.
- **Cursor** — Settings → MCP → Add server, or `.cursor/mcp.json` in your
  project (`~/.cursor/mcp.json` for all projects).
- **Cline** — the MCP Servers icon → Configure, which edits
  `cline_mcp_settings.json`.

Your workspace **guides** ride along automatically in the protocol's
`initialize` `instructions` field — every client above gets your data notes
with zero extra configuration ([how guides work](guides.html)).

## Run it in Docker

The repository ships a `Dockerfile` that runs the MCP server over stdio with a
bundled demo workspace, so it starts and answers introspection out of the box:

```sh
docker build -t datacharter-mcp .
docker run -i --rm datacharter-mcp                       # demo workspace
docker run -i --rm -v "$PWD:/workspace" datacharter-mcp  # your own workspace
```

An MCP client can launch it with `"command": "docker", "args": ["run", "-i",
"--rm", "datacharter-mcp"]`.

## Scope

Default is local and unauthenticated: stdio, or Streamable HTTP on loopback.
To expose `/mcp` on the network, set all three:

```
DATACHARTER_OAUTH_ISSUER=https://auth.example.com
DATACHARTER_OAUTH_AUDIENCE=https://datacharter.example.com/mcp
DATACHARTER_OAUTH_JWKS_URI=https://auth.example.com/.well-known/jwks.json
```

Then `POST /mcp` requires `Authorization: Bearer <JWT>` (RS256, matching
`iss` / `aud` / `exp`). Clients discover the issuer at
`/.well-known/oauth-protected-resource` (RFC 9728). Off by default.

`principals:` and `grants:` in `charter.yaml` then limit that caller to listed
relations (default-deny). Unknown `sub` sees an empty catalog. Stdio MCP is
unchanged (the local owner).

The flight recorder still writes the hash chain. To copy the same metadata
(who, SQL, allow/deny, never rows) to a SIEM:

```
DATACHARTER_AUDIT=json:/var/log/datacharter.ndjson
DATACHARTER_OTLP_ENDPOINT=http://otel-collector:4318
```

See [Audit](audit.html#siem-json-and-otlp).

To run `/mcp` in a cluster, build `packaging/oci/Dockerfile` and install
`chart/` with OAuth values. See [Deploy](deploy.html).

Next: [Plain-English policies →](policies.html)
