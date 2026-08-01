---
title: FAQ
description: Telemetry, offline use, model choice, and how DataCharter compares.
---

[Home](index.html) &middot; [Quick start](quickstart.html) &middot; [charter.yaml](charter-yaml.html) &middot; [Sources](sources.html) &middot; [Agent](agent.html) &middot; [Evals](evals.html) &middot; [Audit](audit.html) &middot; [Policies](policies.html) &middot; [CLI](cli.html) &middot; [MCP](mcp.html) &middot; [Desktop](desktop.html) &middot; [About](about.html) &middot; [FAQ](faq.html)

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
is on, PII columns — both those you declare under `pii` in `charter.yaml` and
those DataCharter auto-detects — are masked (`•••`) before results reach the
model; you can adjust this per source, table, or column with
[`agent_access`](charter-yaml.html#agent_access) or the explorer's left-panel
toggles. With `--local` the model runs on your own machine; with a hosted
endpoint or Claude Code, only the questions and those masked results are sent.

## Which model should I use?

You have three paths:

- **Your Claude Code subscription.** If you have [Claude Code](https://claude.com/claude-code)
  installed and signed in to a Claude plan, click **Connect Claude Code** in the
  chat panel — no API key, no per-token billing.
- **Bring your own endpoint.** Any OpenAI-compatible `/chat/completions` endpoint:
  set `OPENAI_BASE_URL` and `OPENAI_API_KEY`, and choose the model with
  `DATACHARTER_MODEL` (default `gpt-4o-mini`). This can be a hosted API or a
  self-hosted server such as vLLM.
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

## How do I make the agent smarter about *my* data?

Write guides. `guides/*.md` in the workspace holds the context you'd explain to
a colleague ("revenue is net of refunds", "exclude tier = 'internal'"); the
agent surface receives it automatically — including MCP clients, via the
protocol's `instructions` field. Per-table notes go in the charter's
[`context:`](charter-yaml.html#context-and-guides-agent-context) mapping. Start
from the [example workspace](https://github.com/datacharter/datacharter/tree/main/examples/ecommerce).

## How do I know the agent is getting my data right?

Write an [eval suite](evals.html). `evals/*.yaml` holds the questions you ask plus assertions on what a correct answer must contain; `datacharter eval` scores the agent against them, `--compare-guides` shows how much your guides help, and `--threshold` turns it into a CI gate. Runs persist locally so you can watch the trend and catch regressions.

## How do I prove what an agent actually saw?

The [flight recorder](audit.html). Every agent data access is logged with dual
attribution (OS user + the MCP client or model), hash-chained so edits and
deletions are detectable, and exportable as an evidence pack. `datacharter
audit verify` walks the chain; the Audit panel shows the timeline. Metadata and
hashes only — the log never stores raw rows.

## How would I know if masking ever failed?

Enable [canary tripwires](audit.html): `canary: on` plants synthetic honeytokens
in a masked local table. If a token ever appears in agent output, masking
provably failed — the alarm lands in the tamper-evident audit chain, and block
mode withholds the response. `datacharter canary drill` proves the alarm path.

## Is there a version that doesn't need a terminal?

Yes — the [desktop app (beta)](desktop.html): a native macOS/Windows application
wrapping the same local server. Pick a workspace folder and go; every governance
layer applies identically. Downloads are on the latest GitHub release.

## Do I have to write the guides myself?

Not from scratch. `datacharter suggest` mines your recent query history for
repeated habits (filters you always apply, tables you always join) and turns
them into guide suggestions with evidence — accept them in the CLI (`--apply`)
or one-click in the Guides editor. Deterministic and offline; no model needed.

## Can I stop an agent from ever seeing individual rows?

Yes — [policies](policies.html): `aggregates only` restricts a relation to
aggregate queries, `groups of at least k` suppresses any group smaller than k
(the clean-room control), and `no joins to …` blocks re-identification via
joins. Written in plain English in the charter, compiled deterministically,
enforced fail-closed at the agent surface.

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
