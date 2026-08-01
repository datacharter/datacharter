# DataCharter

> **Query all your data locally — then hand your AI agents exactly the data you choose, and not one column more.**

<!-- mcp-name: io.github.datacharter/datacharter -->

[![PyPI](https://img.shields.io/pypi/v/datacharter)](https://pypi.org/project/datacharter/)
[![Python](https://img.shields.io/pypi/pyversions/datacharter)](https://pypi.org/project/datacharter/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue)](LICENSE)
[![DataCharter MCP server on Glama](https://glama.ai/mcp/servers/datacharter/datacharter/badges/score.svg)](https://glama.ai/mcp/servers/datacharter/datacharter)

**[datacharter.dev](https://datacharter.dev)** · [Desktop app (beta)](https://datacharter.dev/desktop.html) · [Docs](https://datacharter.dev/quickstart.html) · [Blog](https://datacharter.dev/blog/) · [CI Action](https://github.com/marketplace/actions/datacharter-data-checks)

*The big-words version: a local, federated data explorer with governed, regulated
agentic data access, powered by **[DuckDB](https://duckdb.org)**.* Here's what that
actually means 👇

**🔍 Query all your data, locally — no pipelines, no warehouse, no waiting**

- Local CSV, Parquet, JSON, and Excel files — or drag one onto the window
- Postgres, MySQL, SQLite, SQL Server, Snowflake, BigQuery, DuckDB, Iceberg, Delta — and more
- JOIN a local CSV → a Snowflake table → a Parquet file in S3, in **one** SQL statement, all on your laptop
- Yes, it's as unreasonable as it sounds. You kind of have to try it to believe it.

**🤖 Connect an agent — and decide exactly what it's allowed to see**

- **Claude Code** — runs on your existing subscription, no API key
- A model running **fully local** with [Ollama](https://ollama.com)
- Any **OpenAI-compatible** agent
- Grant or deny access in the UI *or* right in your data contracts, at every level: whole **sources** → individual **tables** → individual **columns**
- **PII is auto-detected and defaulted to *no agent access*** — override per field if you really mean to
- **Teach it your data's quirks.** Markdown guides in `guides/*.md` ("revenue is net of refunds", "exclude QA accounts") reach every agent — chat, Claude Code, and MCP clients alike. Start from the [end-to-end example](examples/ecommerce).
- **Or let the guide write itself.** `datacharter suggest` mines your query history for the habits you repeat and turns them into guide lines — with evidence, offline, no model required.
- **Measure the lift.** `datacharter eval --compare-guides` scores the agent on questions you write and shows how much your guides moved accuracy — locally, and as a CI gate. See [Agent evals](https://datacharter.dev/evals.html).
- **Prove it happened.** A tamper-evident [flight recorder](https://datacharter.dev/audit.html) logs every agent access — dual attribution, masked columns, hash-chained — with `datacharter audit verify` and one-command evidence packs.
- **Know the moment it fails.** Opt-in [canary tripwires](https://datacharter.dev/audit.html) plant masked honeytokens; if one ever escapes to agent output, you get a tamper-evident alarm — and block mode withholds the response.
- **Clean-room math, one YAML line.** [Policies](https://datacharter.dev/policies.html) like `aggregates only` and `groups of at least 10` are enforced by query analysis — k-anonymity suppression and join limits, written in plain English.
- Don't take our word for it: flip on **Agent view** and see, column by column, exactly what your agent gets back when it runs a query. *(Spoiler: the PII comes back `•••`.)*

## Wait, there's more!

Beyond local federation and governed agent access, you also get:

- **See answers as you type.** Live results preview while you write SQL, one-click auto-charts, and a profiling panel — missing values, distributions, outliers, and per-column top-value bars — no separate BI tool.
- **Never lose a query.** Every run is saved to a local history you can reopen, and a **⌘K command palette** jumps to any table or action.
- **Know the cost before you run.** One click estimates how many rows a query will scan and warns before a big one.
- **Safe by design.** The engine is read-only by construction — no query can write, delete, or touch the filesystem — so pointing an AI (or a teammate) at your real databases can't do damage.
- **Point *other* AI tools at your data, too.** A governed MCP server exposes the same read-only, PII-masked query tools to Cursor, Cline, or your own agent.
- **Every agent answer is reproducible.** The chat shows the exact SQL the agent ran, with one click to open it in the editor — and each result shows which source columns it read, so you always know where a number came from.
- **Save, reuse, export.** Snapshot a result as a reusable local table; export to CSV, Parquet, JSON, or XLSX.
- **Governance you can automate.** From the command line: assert data quality (`datacharter test`), catch schema/PII drift in CI, diff data across sources, trace cross-source lineage, and define certified metrics. Or drop the [GitHub Action](https://github.com/marketplace/actions/datacharter-data-checks) into your workflow and let a broken contract block the PR.

![DataCharter — live SQL preview, auto-charts, per-query provenance, and PII masking](https://raw.githubusercontent.com/datacharter/datacharter/main/brand/demo.gif)

**Status: pre-release.** V1 in development.

## Quick start

> **No terminal? [Download the desktop app](https://github.com/datacharter/datacharter/releases/latest)** (beta) for macOS or Windows — the same governed explorer in a native window. [Desktop docs](https://datacharter.dev/desktop.html).


```sh
# Try it instantly on generated demo data — no install, no config:
uvx datacharter serve          # needs `uv` → https://astral.sh/uv
# → serves at http://127.0.0.1:8321 (open it in your browser)

# Or install it:
brew install datacharter/tap/datacharter   # macOS (Homebrew)
pip install datacharter                     # Python 3.11+ (any OS)

# Start your own workspace:
datacharter init               # scaffolds charter.yaml, queries/, .env.example
# → add a source: edit charter.yaml, or use the "Sources" panel in the UI
datacharter serve              # → http://127.0.0.1:8321
```

Then, once it's running, **drag a CSV, Parquet, or JSON file onto the window** to
query it instantly — no config needed.

**Optional natural-language agent** — point it at any OpenAI-compatible endpoint:

```sh
export OPENAI_BASE_URL=...     # any OpenAI-compatible API
export OPENAI_API_KEY=...
datacharter serve
```

…or run **fully local** — no API key, no data leaves your machine (requires
[Ollama](https://ollama.com)):

```sh
ollama pull qwen3:8b           # once
datacharter serve --local      # qwen3:8b by default (--model to change)
```

## Why DataCharter

- **Your contracts are the catalog.** `charter.yaml` describes sources, tables,
  and PII fields — the same contract spec your data team already writes, so
  there's no separate metadata store to maintain.
- **Real federation, not just a shared connection.** Filters and projections are
  pushed down to each source — even across a cross-source join, every leg is
  filtered where its data lives. (Snowflake runs via connector extract,
  `datacharter[snowflake]`, with the same pushdown into the extract.)
- **Local-first.** One process, your machine, no cloud dependency. The optional
  `--local` agent runs a small open model via Ollama — no API key, no data leaves
  your machine.
- **The workspace is a directory.** `charter.yaml` + `queries/*.sql` +
  `.env.example` — commit it, clone it, `datacharter serve`. Your team's whole
  exploration environment travels as a repo; secrets and local state never do.

DataCharter governs and audits your data, not just displays it. The full command
set (`drift`, `scan`, `diff`, `metric`, `mcp`, and more) is in the
[CLI reference](docs/cli.md); the security model is in [security](docs/security.md).

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

## Privacy

DataCharter runs entirely on your machine. It collects **no** data, sends **no**
telemetry, and operates **no** servers — your data, queries, and credentials never
leave your control except to the sources you configure or a model provider you
explicitly enable. Full policy: **[Privacy Policy](https://datacharter.dev/privacy)**.

## License

[Apache-2.0](LICENSE)
