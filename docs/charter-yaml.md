---
title: charter.yaml reference
description: Every field of a source contract, plus how credentials resolve.
---

[Home](index.html) &middot; [Quick start](quickstart.html) &middot; [charter.yaml](charter-yaml.html) &middot; [Sources](sources.html) &middot; [Agent](agent.html) &middot; [Evals](evals.html) &middot; [Audit](audit.html) &middot; [Policies](policies.html) &middot; [CLI](cli.html) &middot; [MCP](mcp.html) &middot; [Desktop](desktop.html) &middot; [About](about.html) &middot; [FAQ](faq.html)

`charter.yaml` is the heart of a workspace. It describes your sources the way a
data contract does: connection shape, which tables to expose, and which columns
are PII. It never holds secrets. Credentials are `${NAME}` references resolved at
load time from your environment, a local `.env`, or your OS keyring.

## Top-level shape

```yaml
version: 1

sources:
  <source_name>:
    type: <source type>
    # ...fields below
```

| Key | Required | Notes |
| --- | --- | --- |
| `version` | yes | Must be `1`. Any other value is a load error. |
| `sources` | yes | A non-empty **mapping** of source name to source body. |

The file must be a YAML mapping. `sources` is keyed by name (not a list), so
each source name is unique by construction.

## Source name

The mapping key is the source name. It must match `^[a-z][a-z0-9_]{0,62}$`:
lowercase, starting with a letter, using only letters, digits, and underscores,
up to 63 characters. The name becomes the source's catalog alias and the prefix
of its flat table views (`<name>__<table>`).

## Source fields

Every source supports the following fields. Only `type` is always required;
which of the rest apply depends on the source type (see the
[sources matrix](sources.html)).

### `type` (required)

One of: `postgres`, `mysql`, `sqlite`, `bigquery`, `mssql`, `snowflake`,
`csv`, `parquet`, `json`, `iceberg`, `delta`. An unknown value produces an
error listing the valid types.

### `connection`

A mapping of **non-secret** connection parameters. Values are strings or
integers. What each type reads:

| Type | Recognized `connection` keys |
| --- | --- |
| `postgres` | `host`, `port`, `database` (required), `user`, `schema` (default `public`) |
| `mysql` | `host`, `port`, `database`, `user` |
| `mssql` | `host`, `port`, `database` (required), `user`, `schema` (default `dbo`) |
| `bigquery` | `project` (or `project_id`, required), `dataset` (or `dataset_id`) |
| `snowflake` | `account`, `user`, `database`, `schema` (default `PUBLIC`), `warehouse` |
| `sqlite`, file types | none (use `path`) |

Credential-shaped keys are rejected here. If a `connection` key name looks like
a secret (it ends in `password`, `passwd`, `secret`, `token`, `passphrase`,
`api_key`, or `key`), it must be a `${NAME}` reference and belongs under
`credentials`. This keeps secrets out of the contract by construction.

### `credentials`

A mapping of credential names to `${NAME}` references. **Literal values are not
allowed** here: the loader hard-errors on any value that is not a bare `${NAME}`
reference, telling you exactly which key to fix. This is the safe-by-design rule
that lets you commit `charter.yaml`.

What each type reads from `credentials`:

| Type | `credentials` keys |
| --- | --- |
| `postgres`, `mysql`, `mssql` | `password` |
| `snowflake` | `password` or `private_key` |
| file types on `s3://` paths | `key_id`, `secret`, `region`, `endpoint` |

```yaml
credentials:
  password: ${WAREHOUSE_PASSWORD}
```

Because every value under `credentials` must be a reference, even non-secret
S3 settings like `region` are given as references when placed here.

### `path`

For file sources (`csv`, `parquet`, `json`, `iceberg`, `delta`) and `sqlite`.
A local path (resolved relative to the workspace) or a URL
(`s3://`, `gcs://`, `azure://`, `https://`). Inline `${VAR}` references are
interpolated. For portability (workspace concept, D9) the loader **warns** on
absolute paths and on Windows-style backslashes; prefer a workspace-relative,
POSIX-style path or a `${VAR}` reference.

### `tables`

A list of table names to expose for a database or Snowflake source. Each is
published as a flat `<source>__<table>` view. If omitted for a database source,
DataCharter introspects the source and aliases all of its tables. File sources
are a single relation named after the source, so they ignore `tables`.

### `pii`

A mapping of table name to a list of column names that hold PII. These columns
are **masked** (`•••`) in the agent's tool results by default, so sensitive
values are never sent to a model. DataCharter also **auto-detects** likely PII at
serve time and masks it the same way. Masking applies to the agent path (the
built-in agent, [MCP](mcp.html), and Claude Code); the SQL editor returns real
values locally. Override any column with [`agent_access`](#agent_access) below.

```yaml
pii:
  customers: [email, phone]
```

### `agent_access`

Optional. Fine-grained control over what the **agent** may see, overriding the
PII default. Access resolves most-specific-first — a column override beats a
table override, which beats a source-wide override, which beats the PII default
(masked when the column is declared or auto-detected PII, real otherwise).

`true` means the agent sees real values; `false` means it sees masked (`•••`)
values. The human SQL editor is never affected either way.

```yaml
agent_access:
  source: true                 # whole-source default for the agent
  tables:
    orders: true               # every column of orders
  columns:
    customers.tier: false      # mask one non-PII column
    customers.email: true      # unmask one PII column
```

The **data explorer's left panel** writes this block for you: the 👁 / 🙈
toggles on each source, table, and column persist straight into `agent_access`.

### `row_filters`

Optional. Row-level security for the **agent** surface: a mapping of table name
to a SQL boolean predicate. Queries the agent, MCP, or Claude Code run against a
filtered table are rewritten to see only rows matching the predicate; the human
SQL editor is unaffected. Rewriting is fail-closed — if a filtered table is
referenced but the query can't be rewritten, it is refused rather than run
unfiltered.

```yaml
row_filters:
  orders: "region = 'US'"
  customers: "tier != 'internal'"
```

Predicates are static (authored in the contract); the local OSS core has no
per-user principal, so there is no `${...}` interpolation. Combine with `pii`
/ `agent_access` to mask columns *and* restrict rows.

### `max_rows`

An integer greater than zero. The extract cap for a **connector** source
(Snowflake): the connector pulls at most this many rows, then flags the result
as truncated. It overrides the default cap of 1,000,000. It does not apply to
ATTACH or file sources, which stream and are not row-capped; setting it on one
of those produces a warning.

## `local_access`

Optional, top-level. Agent-access overrides for `local.*` **snapshot** relations
(`datacharter snapshot`). Same shape and precedence as a source's
[`agent_access`](#agent_access) — snapshot columns are masked by the PII default,
and this block overrides per column/table. The left panel's 👁 / 🙈 toggles on a
snapshot write here.

```yaml
local_access:
  columns:
    snap.email: true    # let the agent see a snapshotted email column
```

## `context` and guides (agent context)

Two ways to hand agents the context you'd explain to a colleague; both are
served only to the agent surface (built-in chat, Claude Code, and MCP clients),
never injected into the human SQL editor.

**Per-table `context:`** — a sibling mapping in a source (same shape as `pii:`);
`describe_table` returns it alongside the schema:

```yaml
sources:
  crm:
    type: postgres
    tables: [customers]
    context:
      customers: "One row per customer; tier = 'internal' marks QA accounts — exclude them."
```

**Workspace guides** — free-form markdown in `guides/*.md` at the workspace
root. Every file is loaded (alphabetically, capped at 8,000 characters) into the
agent's system context; MCP clients receive it through the protocol's
`initialize` `instructions` field. HTML comments in guides are stripped and
never reach the model. Guides are trusted contract content: version them,
review them in PRs, and they travel with the workspace. See [Agent evals](evals.html) to measure the lift your guides provide. Run `datacharter scan` (or `--strict` in CI) to catch literal PII accidentally pasted into a guide — agents read that text, so it never passes through column masking.

## `policies` (plain English, enforced)

Per-relation rules for the agent surface — sentences or structured keys:

```yaml
policies:
  crm.customers:
    - aggregates only          # no raw rows, DISTINCT, CTEs, or set ops
    - groups of at least 10    # k-anonymity: smaller groups are suppressed
    - no joins to payments     # may not be queried together with payments
```

See [Policies](policies.html) for exact semantics. Unrecognized sentences are a
load error; enforcement fails closed.

## Metrics

Optional, top-level. Declare named, governed aggregations so the agent, the
`metric` CLI, and anyone reading the contract share one definition — a certified
`revenue` always means the same thing.

```yaml
metrics:
  revenue:
    relation: orders                    # base relation (a source table or view)
    expression: sum(orders.total)       # the aggregate expression
    dimensions: [customers.region]      # optional default GROUP BY columns
    time_column: orders.created_at      # optional; enables --grain
    joins:                              # optional joins across sources/tables
      - relation: customers
        on: orders.customer_id = customers.id
        type: left                      # inner (default) | left | right | full
```

Each metric resolves to a single read-only `SELECT`. Run one with
`datacharter metric revenue` — add `--by region` to override the grouping, or
`--grain month` (needs `time_column`; one of day/week/month/quarter/year) to
group by a `date_trunc` of the time column. Joins let a metric span tables:
`FROM relation <type> JOIN <relation> ON <on> …`. The aggregate `expression` and
each join `on` are raw SQL (authored in the trusted contract); relations,
dimensions, `time_column`, the grain, and the join `type` are validated.

## Tests

Optional, top-level. Declare data assertions and run them with `datacharter test`
(which **exits non-zero if any fail** — drop it in CI). Each test is keyed by
name; `type` is one of `not_null`, `unique`, `accepted_values`, `row_count`, or
`expression`.

```yaml
tests:
  orders_id_not_null: { type: not_null, relation: orders, column: id }
  order_id_unique:    { type: unique, relation: orders, columns: [id] }
  region_valid:       { type: accepted_values, relation: customers, column: region, values: [US, EU] }
  has_orders:         { type: row_count, relation: orders, min: 1 }
  totals_nonneg:      { type: expression, relation: orders, expression: "total >= 0" }
```

- `not_null` — `column` must have no NULLs.
- `unique` — `columns` (or `column`) must be unique together.
- `accepted_values` — `column` values must be within `values` (NULLs ignored).
- `row_count` — `count(*)` must be within `min`/`max` (either or both).
- `expression` — a boolean predicate that must hold for every row.

`expression` is raw SQL (trusted contract); relations, columns, and
`accepted_values` literals are validated/quoted. Because tests run through the
read-only engine, they work across every source DuckDB federates. In CI:

```yaml
- run: uvx datacharter test    # non-zero exit fails the job
```

## Secret resolution order

A `${NAME}` reference is resolved in this order, first hit wins:

1. **Process environment** (`export NAME=...`). Best for CI and headless runs.
2. **Workspace `.env`** (next to `charter.yaml`, gitignored). Best for local dev.
3. **OS keyring** (service name `datacharter`). Best on a laptop, where the
   value is stored in the system credential manager rather than a file.

If none resolve, the loader raises an error naming the reference and the stores
it tried. The keyring is accessed through the `keyring` library (the same
mechanism `pip` uses); on a headless machine with no keyring backend, the
environment and `.env` remain the supported paths.

To store a value in the OS keyring under the `datacharter` service:

```sh
keyring set datacharter WAREHOUSE_PASSWORD   # prompts for the value
keyring get datacharter WAREHOUSE_PASSWORD   # verify
```

Secrets are never written into `charter.yaml`, never logged, and are scrubbed
from engine error messages. Inside DuckDB, credentials are injected as
**temporary** (in-memory) secrets, never persisted to disk.

## A full example

```yaml
version: 1

sources:
  # Local files (workspace-relative paths).
  customers:
    type: csv
    path: demo/customers.csv
    pii:
      customers: [email]

  orders:
    type: parquet
    path: demo/orders.parquet

  # A Postgres database over ATTACH. Only `password` is a secret.
  warehouse:
    type: postgres
    connection:
      host: db.internal.example
      port: 5432
      database: analytics
      user: reader
      schema: public
    credentials:
      password: ${WAREHOUSE_PASSWORD}
    tables: [customers, orders, refunds]
    pii:
      customers: [email, phone]

  # BigQuery via a DuckDB community extension (auto-installed on first use).
  events:
    type: bigquery
    connection:
      project: my-gcp-project
      dataset: analytics

  # Snowflake via the connector extract. Materialized locally, row-capped.
  finance:
    type: snowflake
    connection:
      account: myorg-account
      user: reader
      database: FINANCE
      schema: PUBLIC
      warehouse: COMPUTE_WH
    credentials:
      password: ${SNOWFLAKE_PASSWORD}
    tables: [invoices]
    max_rows: 500000

  # A file in object storage. S3 settings live under credentials as references.
  logs:
    type: parquet
    path: s3://my-bucket/logs/2026/*.parquet
    credentials:
      key_id: ${AWS_ACCESS_KEY_ID}
      secret: ${AWS_SECRET_ACCESS_KEY}
      region: ${AWS_REGION}
```

See the [sources matrix](sources.html) for how each type is registered and how
pushdown behaves.
