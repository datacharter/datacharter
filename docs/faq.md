---
title: FAQ
description: Telemetry, offline use, model choice, and how DataCharter compares.
---

[Home](index.html) &middot; [Quick start](quickstart.html) &middot; [charter.yaml](charter-yaml.html) &middot; [Sources](sources.html) &middot; [Agent](agent.html) &middot; [CLI](cli.html) &middot; [MCP](mcp.html) &middot; [About](about.html) &middot; [FAQ](faq.html)

## Does DataCharter collect any telemetry?

No. There is zero telemetry and no phone-home of any kind. The server binds to
`127.0.0.1` by default, so it is reachable only from your machine unless you opt
in with an explicit `--host`.

## Can I use it fully offline?

Yes, with one caveat about first use. The application, engine, and UI run
locally with no network calls. DuckDB fetches source extensions (for example,
the community BigQuery and SQL Server extensions, or the Iceberg and Delta core
extensions) from its extension repository the first time they are used, which
needs network access once. After that, and for sources that use bundled
extensions or local files, no connection is required. The optional agent needs
network access only if you point it at a hosted endpoint; with `--local` it stays
on your machine.

## Where does my data go? Is anything sent to a model?

Query results stay local. The natural-language agent is optional. If you do not
configure an endpoint or run `--local`, no data is sent anywhere. When the agent
is on, columns you list under `pii` in `charter.yaml` are masked before results
are sent to the model, and with `--local` the model runs on your own machine.

## Which model should I use?

Any model behind an OpenAI-compatible `/chat/completions` endpoint works. You
have two paths:

- **Bring your own endpoint.** Set `OPENAI_BASE_URL` and `OPENAI_API_KEY`, and
  choose the model with `DATACHARTER_MODEL` (default `gpt-4o-mini`). This can be a
  hosted API or a self-hosted server such as vLLM.
- **Fully local.** `datacharter serve --local` uses [Ollama](https://ollama.com)
  with `qwen3:8b` by default; override with `--model`.

There is no bundled or fine-tuned model. Grounding (schema introspection,
contract scoping, execution-feedback retry) does the heavy lifting, so a capable
general model is usually enough. See [Agent modes](agent.html) for details.

## Is it free? Can my company use it?

Yes. DataCharter is released under the
[Apache-2.0 license](https://github.com/datacharter/datacharter/blob/main/LICENSE),
which permits commercial use.

## Do I need Docker, an account, or a database to run it?

No. DataCharter is one Python package that runs as a single process. Docker is
used only in the project's own integration tests, never required of users. There
is no account and no application database; local state is a DuckDB file inside
the workspace.

## Is the engine read-only?

Yes. A statement allowlist is enforced in the engine, so queries cannot modify
your sources. The only write path is `local.*` DDL, used for snapshots into the
workspace's encrypted local catalog.

## How does it compare to other tools?

At a high level, and without disparaging any of them (they are good tools):

- **Datasette** is excellent for exploring and publishing SQLite databases as a
  browsable site and JSON API. DataCharter is exploration-first rather than
  publishing-first, federates many source types beyond SQLite through DuckDB, and
  adds contract-declared sources, PII masking, profiling, and an optional agent.
- **DuckDB web UIs (such as Duck-UI)** put a browser front-end on DuckDB SQL.
  DataCharter also builds on DuckDB, and adds contract-governed multi-source
  federation, per-source pushdown, a profiling panel, an optional natural-language
  agent, and the portable-workspace concept (a workspace is one committable
  directory).
- **WrenAI** focuses on natural-language BI over a semantic layer, typically
  deployed as a set of services against your warehouse. DataCharter is a single
  local process where the contract (not a separate semantic layer) governs
  sources and the agent is entirely optional; nothing else depends on it.

The short version: DataCharter's angle is contract-governed, local-first
exploration across many sources, where the agent is a bonus rather than the
point.

## Why "charter"?

Your `charter.yaml` is the contract that charters the workspace: it declares the
sources, the tables, and the sensitive fields. Charter your data, then explore
it.
