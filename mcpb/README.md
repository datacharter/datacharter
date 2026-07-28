# DataCharter — Claude Desktop extension (MCPB)

This directory packages DataCharter's governed MCP server as an [MCP Bundle
(MCPB)](https://github.com/modelcontextprotocol/mcpb) — a one-click desktop
extension for Claude Desktop.

It exposes four **read-only, PII-masked** tools over MCP — `list_sources`,
`list_tables`, `describe_table`, and `query` — over your own data, federated
through DuckDB and governed by a YAML `charter.yaml`.

## Install (from the packed bundle)

1. Build the bundle: `npx @anthropic-ai/mcpb pack` (produces `datacharter.mcpb`).
2. In Claude Desktop → **Settings → Extensions**, drag in `datacharter.mcpb`.
3. When prompted, choose your **Workspace directory** — the folder containing your
   `charter.yaml`. That's it.

The host manages the Python/uv runtime and installs `datacharter` from PyPI on
first launch; no separate Python setup is required.

## How it runs

`uv run server/main.py`, which launches `datacharter mcp <workspace>`. The workspace
directory is passed via the `DATACHARTER_WORKSPACE` environment variable, set from
the extension's user config.

## Privacy Policy

DataCharter runs entirely on your machine. It collects **no** data, sends **no**
telemetry, and operates **no** servers — your data, queries, and credentials never
leave your control except to the sources you configure or a model provider you
explicitly enable. Full policy: <https://datacharter.github.io/datacharter/privacy>.
