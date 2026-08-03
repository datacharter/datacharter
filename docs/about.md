---
title: About DataCharter
description: Why contract-governed local data exploration exists.
---

[Home](index.html) &middot; [Quick start](quickstart.html) &middot; [Editor](editor.html) &middot; [charter.yaml](charter-yaml.html) &middot; [Sources](sources.html) &middot; [Agent](agent.html) &middot; [Guides](guides.html) &middot; [Evals](evals.html) &middot; [Audit](audit.html) &middot; [Policies](policies.html) &middot; [CLI](cli.html) &middot; [MCP](mcp.html) &middot; [Workspace](workspace.html) &middot; [Desktop](desktop.html) &middot; [About](about.html) &middot; [FAQ](faq.html)

## The idea

Data teams already describe their data. They write data contracts: which sources
exist, which tables and columns they hold, which fields are sensitive. That
description usually sits in a catalog or a spec file and does little for the
person who just wants to look at the data.

DataCharter turns that description into a working tool. Your `charter.yaml` is
the catalog: point it at your sources, and you get one local window that can
query, join, chart, and profile across all of them. The contract you already
maintain becomes the thing you explore through.

## What it is

DataCharter is a single local application: a DuckDB federation engine, a FastAPI
server, and a web UI, shipped as one Python package. Run one command and you
have a workspace in your browser.

- **Contract-governed.** Sources are declared in `charter.yaml`, an
  ODCS-compatible YAML contract. PII columns — declared, or auto-detected — are
  masked from the agent by default, and you choose exactly what any agent may see,
  per source, table, or column. Secrets are never in the file; they are `${NAME}`
  references.
- **Local-first.** One process on your machine, binding to localhost by default.
  No cloud dependency, no account, and zero telemetry of any kind.
- **Federated.** Postgres, MySQL, SQLite, BigQuery, SQL Server, files, Iceberg,
  Delta, and Snowflake, joined through one engine, with filters and projections
  pushed down to each source.
- **Portable by contract.** A workspace is one directory: contract, queries, and
  an example env file travel as a repo. Secrets and local state never do.

## Why local, why now

Exploring data should not require standing up a service, granting a SaaS access
to your warehouse, or shipping rows to someone else's cloud. Modern analytical
engines run comfortably on a laptop, and most contracts a team writes are small
text files. Putting the two together yields a tool that is fast, private, and
easy to share as source.

Keeping it local also makes the natural-language agent honest. The agent is
optional and can run entirely on your machine against a local model, on your
Claude Code subscription, or on any hosted endpoint. Whichever you pick, PII is
masked before anything is sent (and you control what else the agent may see), and
the engine stays read-only regardless of what the model suggests.

## What it is not

DataCharter is deliberately small. It is not a BI platform, not a data catalog
service, not an orchestration tool, and not a multi-user application with its own
auth system. It is a local tool for exploring the data your contracts already
describe. Its extension surface is DuckDB's own extension ecosystem rather than a
bespoke plugin system.

## Who builds this

DataCharter is built by [Rishi Mashelkar](https://github.com/rishi-mashelkar),
a data engineer who wanted to point AI agents at real data without the
governance nightmare. You can find him on
[GitHub](https://github.com/rishi-mashelkar) and
[LinkedIn](https://www.linkedin.com/in/rishimashelkar/), or say hi at
[hello@datacharter.dev](mailto:hello@datacharter.dev) — feedback and issue
reports genuinely shape the roadmap.

## Built on open source

DataCharter stands on excellent open-source foundations: DuckDB for the engine
and federation, the Open Data Contract Standard for the contract format,
Vega-Lite for charting, and Monaco for the SQL editor. It is released under the
[Apache-2.0 license](https://github.com/datacharter/datacharter/blob/main/LICENSE),
which permits commercial use.

DuckDB is a trademark of the DuckDB Foundation. DataCharter is an independent
project and is not affiliated with or endorsed by the DuckDB Foundation.
