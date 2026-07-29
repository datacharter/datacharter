# Installing DataCharter as an MCP server

DataCharter is a local, governed MCP server. Setup is one command — no API key,
no account, nothing hosted.

## 1. Prerequisites

- **Python 3.12+** and **[uv](https://astral.sh/uv)** (provides `uvx`).

## 2. Pick a workspace

DataCharter serves the data sources declared in a `charter.yaml`. Point it at a
folder that contains one:

- **Existing project:** use the folder that holds your `charter.yaml`.
- **New / demo:** run `uvx datacharter init <folder>` to scaffold a `charter.yaml`,
  or `uvx datacharter serve` for an instant demo workspace to try it out.

## 3. Add the MCP server config

Add this block to your MCP settings (for Cline, that's `cline_mcp_settings.json`):

```json
{
  "mcpServers": {
    "datacharter": {
      "command": "uvx",
      "args": ["datacharter", "mcp", "/absolute/path/to/your/workspace"]
    }
  }
}
```

Replace `/absolute/path/to/your/workspace` with your workspace folder (the one
containing `charter.yaml`).

## What you get

Four **read-only, PII-masked** tools over stdio MCP:

- `list_sources` — configured data sources and their types
- `list_tables` — all queryable tables (fully-qualified relation names)
- `describe_table` — columns and types for a relation
- `query` — run a read-only SQL query (PII masked, row-level security enforced)

## Verify it started

On launch the server prints `datacharter MCP server on stdio (<workspace>)` to
**stderr** (stdout carries the protocol). Every tool is read-only, so it is safe
to point at real databases. Full docs: <https://datacharter.dev/mcp>.
