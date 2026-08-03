---
title: MCP server — connect Claude, Cursor, or Cline to your data, governed
description: Expose your workspace to any MCP client — read-only, PII-masked SQL over your files and databases, with per-column access from your data contract.
---

[Home](index.html) &middot; [Quick start](quickstart.html) &middot; [Editor](editor.html) &middot; [charter.yaml](charter-yaml.html) &middot; [Sources](sources.html) &middot; [Agent](agent.html) &middot; [Guides](guides.html) &middot; [Evals](evals.html) &middot; [Audit](audit.html) &middot; [Policies](policies.html) &middot; [CLI](cli.html) &middot; [MCP](mcp.html) &middot; [Workspace](workspace.html) &middot; [Desktop](desktop.html) &middot; [About](about.html) &middot; [FAQ](faq.html)

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
datacharter mcp            # serve the workspace in the current directory
datacharter mcp /path/to/workspace
```

The server speaks JSON-RPC 2.0 over stdio (standard input/output). A charter is
required — run `datacharter init` first if you don't have one. Diagnostics are
written to standard error; standard output carries only the protocol.

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

This is the local, single-user surface: stdio transport, no authentication —
the same trust model as running `datacharter serve` on your own machine. A
network-addressable server with per-caller authentication and authorization is a
separate, enterprise-oriented capability and is not part of this command.

Next: [Plain-English policies →](policies.html)
