---
title: CLI reference
description: Every datacharter command, with usage and options.
---

[Home](index.html) &middot; [Quick start](quickstart.html) &middot; [Editor](editor.html) &middot; [charter.yaml](charter-yaml.html) &middot; [Sources](sources.html) &middot; [Agent](agent.html) &middot; [Guides](guides.html) &middot; [Evals](evals.html) &middot; [Audit](audit.html) &middot; [Policies](policies.html) &middot; [CLI](cli.html) &middot; [MCP](mcp.html) &middot; [Workspace](workspace.html) &middot; [Desktop](desktop.html) &middot; [About](about.html) &middot; [FAQ](faq.html)

Every command takes an optional workspace `directory` (default: the current one).
Run `datacharter <command> --help` for the exact flags.

## Setup

### `init [directory] [--demo] [--force]`
Scaffold a workspace: `charter.yaml`, `queries/`, `.env.example`, `.gitignore`.
`--demo` includes a generated demo dataset; `--force` overwrites an existing
`charter.yaml`.

### `demo [directory]`
A zero-config, narrated walkthrough of the governance — no server, no account.
Scaffolds a throwaway demo workspace (or uses one you point it at) and shows what
an AI agent actually sees through the governed tools: **PII masked** (with the raw
value shown alongside so the difference is visible), **writes refused**, the
**contract in control**. Ends by pointing you at `serve` / `mcp` to keep exploring.
Try it in one command: `uvx datacharter demo`.

### `connect [directory] [--client NAME] [--serve-url URL]`
Print the ready-to-paste MCP-server config for popular clients — the file it goes
in, and a **one-click install deeplink** where the client supports one — so you
don't hand-edit JSON. Clients: `claude-desktop`, `claude-code`, `cursor`, `vscode`
(uses the `servers` key, not `mcpServers`), `cline`, `windsurf`, `lmstudio` (or
`all`, the default). Uses an absolute binary path so a GUI-launched client's minimal
`PATH` still finds it. With `--serve-url`, emits HTTP config for a running
`datacharter serve` instead of the local stdio server.

### `import dbt <manifest.json> [-o path] [--force]`
Generate a `charter.yaml` from a dbt project's `target/manifest.json`. The
warehouse type comes from the dbt adapter; models + sources become tables grouped
by database/schema; columns flagged PII in dbt (`meta: {pii: true}` or a
`pii`/`sensitive`/`phi` **tag**, BigQuery policy tags) become masked columns; and
model/source descriptions become per-table agent context. Connection host and
credentials aren't in the manifest, so they're written as `${ENV}` placeholders to
fill in. Turns a whole dbt project into a governed contract in one command.

### `import odcs <contract.yaml|.json> [-o path] [--force]`
Generate a `charter.yaml` from an [Open Data Contract Standard](https://bitol.io)
(ODCS) `DataContract`. The source type + connection come from `servers`; each
`schema` object becomes a table; a property classified `PII`/`sensitive`/…
(or tagged `pii`) becomes a masked column; descriptions become agent context.
DataCharter reads the open standard, so an existing data contract adopts governance
in one step.

### `export odcs [directory] [-o path]`
Publish your `charter.yaml` as an ODCS `DataContract` — each source a `server`,
each table a `schema` object, each declared-PII column classified `PII`. Prints to
stdout or writes a file. Round-trips with `import odcs`, so DataCharter plugs into
the data-contract ecosystem in both directions.

### `serve [directory]`
Start the local web app (API + UI) on `http://127.0.0.1:8321`.

| Flag | Effect |
| --- | --- |
| `--host` | Bind address (default `127.0.0.1`, localhost only). |
| `--port` | Port (default `8321`). |
| `--local` | Use a local Ollama model for the agent. |
| `--model` | Model name to use with `--local`. |
| `--no-spill` | Fail queries instead of spilling to disk (regulated environments). |
| `--offline` | No-egress mode: disable the LLM agent and write a no-egress attestation. |

In the UI, flip **Agent view** on any result to preview it with PII columns
masked — exactly what the agent and the [MCP server](mcp.html) see.

**Resource limits (any engine command).** `DATACHARTER_DUCKDB_MEMORY_LIMIT`
(e.g. `2GB`) caps DuckDB's memory so a heavy query spills or errors within budget
instead of OOM-killing a container; unset, it derives ~80% of a detected container
memory limit, else leaves DuckDB's own default. `DATACHARTER_DUCKDB_THREADS` pins
the thread count.

### `secrets set|list|rm <name>`
Manage `${NAME}` secrets in the OS keyring. `set` prompts without echo (or pass
`--value`); `list` shows names only; `rm` removes one.

## Explore and govern

### `mcp [directory] [--serve-url URL]`
Run a [Model Context Protocol](mcp.html) server over stdio, exposing the four
governed query tools to any MCP client — read-only, PII-masked. With
`--serve-url`, the server proxies tool calls to an already-running
`datacharter serve` instead of opening its own engine (this is how the in-app
Claude Code integration bridges to the governed toolbox); without it, it opens
the workspace directly.

### `diff <left> <right> [directory] [--key cols]`
Diff two relations across sources: rows only in each side plus the common count.
With `--key`, rows are matched by key and changed rows are counted separately.

### `explain <sql> [directory]`
Show a query's plan and `~N rows` estimates **without running it** — a pre-flight
cost check.

### `query <sql> [directory] [--format table|csv|json]`
Run a read-only SQL query across your sources and print the result — federated
joins, the same read-only guard as the app. `--format` selects table (default),
CSV, or JSON output.

Relation names: sources are queried as `source.table` (e.g.
`store.customers`); tables listed under a source's `tables:` also get flat
`source__table` views. Run `datacharter query "SHOW ALL TABLES"` to list every
queryable relation.

### `sample <relation> [directory] [--rows N]`
Print a PII-masked CSV sample of a relation (contract PII columns come back as
`•••`), safe to paste into a ticket. Default 10 rows.

### `scan [directory] [--write]`
Suggest PII columns for `charter.yaml` by column name and by sampled values.
`--write` merges the suggestions into `charter.yaml` (round-trip; credential
references are left untouched).

### `drift [directory] [--update]`
Report schema drift against the baseline saved in `.datacharter/schema.json`
(written automatically on first run): changed columns, and declared tables or
PII columns that no longer exist in the live sources (a missing PII column is a
masking gap). Exits non-zero on drift — usable as a CI gate. `--update` accepts
the current schema as the new baseline.

### `metric <name> [directory] [--by cols] [--grain g]`
Run a contract-defined [metric](charter-yaml.html#metrics) — a named aggregation
declared under `metrics:` — resolved to one governed query. `--by` overrides the
grouping dimensions; `--grain day|week|month|quarter|year` groups by a
`date_trunc` of the metric's `time_column`.

### `access diff [directory] [--against git:REF | --old PATH] [--new PATH] [--json | --md] [--fail-on widened]`
An **Access Plan** — `terraform plan` for AI data access. Diffs the *effective
agent-visible surface* between two charter versions and classifies every change
as **WIDENED** (agent can now see more), **NARROWED** (more protection), or
neutral: a table granted, a PII column unmasked, `min group size` lowered, a
`no joins to` dropped, a row filter removed — all called out in plain English
before it takes effect. It reads the *declared* governance only (no source
connection), so it runs offline and needs no credentials in CI.

By default the old side is `git:HEAD` (the committed charter); pass `--against
git:main~1` for any ref, or `--old PATH` to compare two files directly. `--json`
and `--md` emit machine- and PR-comment-friendly reports. **`--fail-on widened`
exits `2` if any change widens the surface** — drop it into the GitHub Action to
block a PR that quietly widens what an agent can see:

```yaml
# .github/workflows/access.yml — block PRs that widen agent data access
- run: pipx run datacharter access diff --fail-on widened
```

Because the whole governance surface is a file in git, agent data access can be
code-reviewed like any other change — something a runtime-state governance server
structurally can't offer. For wiring `test`, `drift`, and this check into Dagster,
Airflow, or CI as run-blocking gates, see
[Governance gates for data pipelines](pipeline-gates.html).

### `risk <sql> [directory] [--json] [--fail-on low|medium|high]`
**Query-intent risk scoring.** Grade *how risky a query's shape is* before it runs
— so a governed surface can graduate its response by intent, which static
table/column RBAC can't express. A transparent, capped heuristic reads the SQL text
and the contract's PII list (no data): `SELECT *`, naming PII columns, whole-row
serialization (`to_json`/`string_agg` — a masking-evasion shape), unbounded reads,
set-operation differencing, multi-join re-identification, and honeytoken
references each carry a **named weight**. Prints a 0–100 score and band
(low/medium/high) with the reasons, or `--json`. `--fail-on medium|high` exits `2`
at that band — a step-up/deny gate.

### `subject-access <value> [directory] [--column email] [-o file]`
**Subject-access receipt (DSAR).** Produce a signed record of exactly what an AI
agent can see about one person — GDPR Art. 15 / EU AI Act transparency, answered
from the data plane. It looks the subject up by key column (`--column`, default
`email`) across every governed relation that carries it, and seals the result with
the workspace [provenance](provenance.html) key. What the receipt shows is what the
agent sees: **PII columns come back masked** (`•••`). Verify it offline with
`datacharter provenance verify`. `-o` writes the receipt to a file.

### `synth <relation> [directory] [--rows N] [--format csv|json] [-o file] [--seed S]`
**Governed synthetic data.** Generate realistic rows that match a relation's schema
but hold no real data — PII columns come out as clearly-synthetic stand-ins
(`user1234@example.com`, `+1-555-01xx`), never a real value. Because the generator
reads the *same* `charter.yaml` that guards production, your dev/test/CI fixtures
inherit the same PII policy. `--rows` sets the count (default 100), `--seed` makes
output reproducible, `-o` writes a file, `--format` selects CSV (default) or JSON.

### `dp <sql> [directory] [--epsilon E] [--bound B] [--budget C] [--status] [--reset]`
**Differential-privacy query mode.** Add calibrated Laplace noise to an aggregate
answer and spend from a per-workspace **ε budget** — so an agent can't chain
"safe" aggregates to difference-out one individual. Supports **COUNT** (sensitivity
1) and **SUM** (pass `--bound B`, the value range, as its sensitivity); each result
row is assumed to cover distinct individuals (bounded contribution). `--epsilon`
sets the per-query privacy loss (default 1.0); `--budget` the workspace cap
(default 5.0, sequential composition). When a query would exceed the budget it is
**refused**. `--status` shows spent/remaining; `--reset` clears it. Row-level
(non-aggregate) queries are refused — noise there would leak the rows. The scope
and assumptions are stated plainly: DP done wrong is false security, so the
mechanism, sensitivity, and accounting are all explicit.

### `asof <ref> [directory] [--query SQL | --relation R] [--rows N] [--json]`
**Governance time-travel.** Reconstruct the agent-visible surface as it existed at
a git ref — "what would the agent have seen under last March's rules?". With no
`--query`/`--relation` it prints the surface as of that charter version (tables,
masked columns, row filters, `surface_hash`). With `--query` or `--relation` it
runs the query against *current* data but masks it by *that ref's* PII rules, so
you can replay a question under an older policy. Versions the **governance**, not
just the data — the same masked column can come back raw at an earlier ref and
`•••` today, proving exactly when a rule took effect.

### `monitor [directory] [--json] [--no-gauntlet]`
**Continuous compliance.** Run every governance gate in one pass — `test`,
`drift`, `access diff --fail-on widened` (vs `git:HEAD`), and the `redteam`
gauntlet — and report a single status. Each gate is the real command's code, so a
green monitor is evidence about what actually runs. **Exits non-zero if any gate
reports a violation**, so a scheduler (cron, a CI schedule) turns point-in-time
`evidence` into a repeatable, alertable signal. `--json` emits the per-gate report
for alerting; `--no-gauntlet` runs the fast gates only.

### `test [directory] [--select name]`
Run the [data assertions](charter-yaml.html#tests) declared under `tests:` and
**exit non-zero if any fail** — for CI. `--select` runs one test by name.

### `lineage [directory] [--relation R] [--json]`
Show cross-source lineage aggregated from your local query history: which
relations get read together, and which output columns derive from which inputs.
`--relation` filters to one relation; `--json` emits the graph for tooling.
History is recorded as you run queries in the app.

### `openlineage [directory] [--url URL] [--namespace NS] [--job NAME] [-o file]`
Emit the governed catalog as an OpenLineage `COMPLETE` RunEvent — one event whose
inputs are every governed relation, each with a schema facet (columns + types) and
a custom governance facet recording which columns are PII, which are masked on the
agent surface, and the read-only guarantee. `--url` posts to any OpenLineage
receiver (Marquez, DataHub, OpenMetadata) at `<url>/api/v1/lineage`; `-o` writes
the event JSON to a file; with neither it prints the event to stdout. Reads live
schemas, so sources must be reachable. Built on the stdlib — no OpenLineage client
dependency. Verified end-to-end against Marquez.

### `provenance keygen|pubkey|seal|verify`
Signed, independently-verifiable **answer-provenance receipts** — the AI answer you
can take to a regulator or an auditor. `keygen` creates the workspace's Ed25519
signing key; `pubkey` prints the public key to publish. `seal <sql>` runs the query
through the governed surface and emits a signed receipt sealing the query, the
relations read, the masked columns, the row count, a result hash, the governance
`surface_hash`, and the audit-chain head. `verify <receipt>` checks it offline —
recompute the hash, verify the signature, and (`--pubkey`) pin the key; `--flight
<dir>` also confirms the Merkle link into the audit chain. See
[Verifiable answer provenance](provenance.html) for the receipt format and
verification algorithm.

### `snapshot <name> <sql> [directory]`
Save a query's result as `local.<name>` along with its SQL.

### `recheck <name> [directory]`
Re-run a snapshot's query on current data and diff it against the saved result —
"did this number change?". Exits non-zero when the result has changed.

## Govern and prove

### `eval [directory] [--suite name] [--compare-guides] [--judge] [--threshold N] [--local] [--history]`
Run the [agent evals](evals.html) declared in `evals/*.yaml`: each question is
asked of a real agent and scored against your assertions. **Requires an agent
endpoint** — set `OPENAI_BASE_URL` / `OPENAI_API_KEY` (any OpenAI-compatible
endpoint) or pass `--local` for Ollama; with none configured the command
refuses with a hint rather than reporting a misleading 0%. `--compare-guides`
runs each case with and without your guides and reports the lift;
`--threshold 0.8` exits non-zero below 80% (CI gate); `--history` shows past
runs.

### `audit [directory] [verify|export] [--since T] [--until T]`
Read the [flight recorder](audit.html). Bare `audit` lists recorded agent
sessions; `audit verify` re-checks the hash chain and names the exact entry if
anything was tampered with; `audit export` writes a self-contained evidence
pack (entries, verification result, the charter at export time, summary).

### `canary [directory] [drill]`
Show [canary tripwire](audit.html#canary-tripwires) status — whether honeytokens are
planted and armed. `canary drill` deliberately trips one so you can see exactly
what an alarm looks like in the audit chain.

### `redteam [directory]`
**The Gauntlet** — DataCharter attacks its own governance and hands you a report
card. A static, offline battery of attacks (PII exfiltration through
expression-wrapping and whole-row serialization, read-only bypass via writes /
`COPY TO` / `ATTACH` / `PRAGMA` / filesystem functions, policy evasion, and
honeytoken theft) is fired through the **real** governed tool path, so a green
result is evidence about the code that actually runs — not a mock. The oracle
uses the canary honeytokens as ground-truth secrets (planted for the run even if
`canary:` is off), so pass/fail is deterministic and needs zero knowledge of
your data. **Exits 1 on any breach** — drop `datacharter redteam` into CI to
prove your charter's governance still holds on every change. The run is recorded
to the flight recorder.

### `govbench [directory] [--json] [--min-grade A|B|C|D]`
**GovBench — the open benchmark for AI-data governance.** Run the real `redteam`
attack battery through the governed tools, then **grade** the result (A–F) against
defense-in-depth posture — canaries armed, policies active, signed provenance,
declared PII, contract tests. **Any breach fails the grade outright**: you can't
score well while an attack succeeds. Among charters that withstand everything, the
grade rewards how much protection is actually configured. Prints a scorecard with
score, per-attack result, and posture, or `--json`. `--min-grade B` exits 1 below
that grade — a governance-posture gate for CI. The battery is offline and
deterministic, so the number is reproducible anywhere: the yardstick every buyer
can run.

### `suggest [directory] [--apply]`
Mine your workspace's query history for repeated habits your
[guides](guides.html) don't mention yet, and propose guide lines with the
evidence for each. Needs some accumulated history to fire. `--apply` appends
accepted suggestions to your guides.
