# DataCharter

> Explore all your data locally, in one place — contract-governed data exploration, powered by DuckDB

[![PyPI](https://img.shields.io/pypi/v/datacharter)](https://pypi.org/project/datacharter/)
[![Python](https://img.shields.io/pypi/pyversions/datacharter)](https://pypi.org/project/datacharter/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue)](LICENSE)

Contract-governed local data exploration, **powered by [DuckDB](https://duckdb.org)**.
Define your sources as data contracts
([ODCS](https://bitol-io.github.io/open-data-contract-standard/)-compatible YAML),
query them through DuckDB's SQL federation engine with real source pushdowns,
and explore in a local web UI — SQL editor with live preview, auto-charts,
profiling. Every answer shows which source columns it read; ask questions in
plain language or serve the whole thing to an AI agent over [MCP](docs/mcp.md),
with PII masked from the model — all on your machine.

![DataCharter — live SQL preview, auto-charts, per-query provenance, and PII masking](https://raw.githubusercontent.com/datacharter/datacharter/main/brand/demo.gif)

**Status: pre-release.** V1 in development.

## Quick start

```sh
# Try it instantly on generated demo data — no config, nothing to install globally:
uvx datacharter serve
# → opens a local workspace on http://127.0.0.1:8321

# Or install it:
pip install datacharter

# Start a real workspace:
datacharter init            # scaffolds charter.yaml, queries/, .env.example
datacharter serve           # explore in your browser

# Natural-language agent — bring your own endpoint…
export OPENAI_BASE_URL=...  # any OpenAI-compatible API
export OPENAI_API_KEY=...
datacharter serve
# …or run fully local (no API key, no data leaves your machine):
datacharter serve --local   # uses Ollama (qwen3:8b by default)
```

Drop a CSV, Parquet, or JSON file onto the window to query it instantly.

## Why

- **Your contracts are the catalog.** `charter.yaml` describes sources, tables,
  and PII fields — the same contract spec your data team already writes.
- **One engine, every source.** Postgres, MySQL, SQLite, BigQuery, SQL Server,
  S3/GCS/Azure files, Iceberg, Delta — federated joins across all of them, with
  filters and projections pushed down where the data lives — even across a
  cross-source join, each leg is filtered at its source. Snowflake is supported
  via connector extract (`datacharter[snowflake]`) with filters/projections
  pushed into the extract. Every source's tables are exposed under one flat
  `source__table` naming scheme.
- **Local-first.** One process, your machine, no cloud dependency. Optional
  `--local` agent mode runs a small open model via Ollama — no API key, no data
  leaves your machine.
- **The workspace is a directory.** `charter.yaml` + `queries/*.sql` +
  `.env.example` — commit it, clone it, `datacharter serve`. Your team's whole
  exploration environment travels as a repo; secrets and local state never do.

## More than a viewer

DataCharter governs and audits your data, not just displays it — see the
[CLI reference](docs/cli.md) for the full command set:

- **Governed MCP server** — `datacharter mcp` exposes read-only, PII-masked query
  tools to any MCP client (Cursor, Cline, or your own agent).
- **Contracts you can check** — `datacharter drift` exits non-zero when a declared
  table or PII column disappears; `datacharter scan` detects PII columns to add.
- **Answers that show their work** — every result reports the source columns it
  read; `datacharter diff` compares relations across sources; `datacharter metric`
  runs governed metric definitions.
- **Privacy-first** — `serve --offline` runs with no outbound network, and the
  model never sees raw PII (flip **Agent view** in the UI to see exactly what it does).

## Built on

DataCharter stands on excellent open-source foundations:

- **[DuckDB](https://duckdb.org)** — the analytical engine at our core:
  federation (`ATTACH`), file formats, Iceberg/Delta, encryption, autocomplete.
- **[Open Data Contract Standard](https://bitol-io.github.io/open-data-contract-standard/)** /
  [datacontract.com](https://datacontract-specification.com/) — the contract format `charter.yaml` speaks.
- **[Model Context Protocol](https://modelcontextprotocol.io)** — the open protocol
  the `datacharter mcp` server speaks to agents and MCP clients.
- **[Vega-Lite](https://vega.github.io/vega-lite/)** — declarative charting.
- **[Monaco Editor](https://microsoft.github.io/monaco-editor/)** — the SQL editor.
- **[TanStack Table & Virtual](https://tanstack.com/)** — the virtualized results grid.
- And the Python & React ecosystems — FastAPI, pydantic, httpx, keyring, and
  ruamel.yaml on the backend; React and Vite on the front.

Testing uses **[VidaiMock](https://github.com/vidaiUK/VidaiMock)**, an
Apache-2.0 mock LLM server, as the offline agent endpoint in CI.

DuckDB is a trademark of the DuckDB Foundation. DataCharter is an independent
project and is not affiliated with or endorsed by the DuckDB Foundation.

## License

[Apache-2.0](LICENSE)
