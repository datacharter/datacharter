# Changelog

All notable changes to this project will be documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.4.1] - 2026-07-25

### Security

- The governed agent surface (built-in agent, MCP, and Claude Code) now refuses
  a query that uses a masked (PII) column to filter, join, group, or order —
  closing a way an agent could infer masked values by predicate (e.g.
  `WHERE email = '…'` or `ORDER BY email`). A masked column can still be
  selected (its values return as `•••`). The local human SQL editor is
  unaffected.

### Fixed

- "Agent view" is now consistent across the whole result surface: the Chart tab
  drops masked columns (so no raw PII reaches the plotted data), and Export
  downloads a masked `…-agent-view` file while Agent view is on. Previously only
  the results grid honored the toggle.
- Snowflake `NUMBER` columns are extracted with their true precision/scale
  (`BIGINT`/`HUGEINT`/`DECIMAL`) instead of `DOUBLE`, so large integer keys and
  exact decimals are no longer silently corrupted beyond 2^53.

## [0.4.0] - 2026-07-25

### Added

- **Connect Claude Code:** run the chat agent on your local Claude Code subscription (no
  API key) instead of an OpenAI-wire LLM — surfaced beside "Connect an LLM". Data stays
  governed (Claude reaches it only through datacharter's read-only, PII-masked tools via a
  loopback bridge), and the connection is refused, fail-closed, unless the tool sandbox
  verifies (auto-denying any non-governed tools). Requires a Claude Pro/Max subscription +
  Claude Code installed.
- **Per-field agent-access toggles (left panel):** control per field / table / source
  whether the agent sees real values or masked (`•••`) ones, persisted to the contract
  (`agent_access:`). PII (declared or auto-detected) defaults to masked; everything else to
  real; an explicit toggle wins. Enforced on the agent surface only (agent, MCP, Claude
  Code) — the human SQL editor is never masked. "Agent view" mirrors the toggles.
- Remove snapshots and uploaded tables directly from the sidebar (a ✕ on `local.*` and
  uploaded rows), via `DELETE /api/snapshot/{name}` and `DELETE /api/uploads/{name}`.

### Fixed

- The sidebar listed each attached-source table twice — once correctly and once as a fake
  "upload" — because the engine's internal `<source>__<table>` compatibility views were
  included in the catalog listing. They're now hidden.

## [0.3.4] - 2026-07-24

### Added

- Empty workspaces get an "add your data" first-run launchpad (add a source / drop a
  CSV / load the demo dataset) instead of the demo feature-tour, which now auto-shows
  only when the workspace has sources. New `POST /api/demo` loads the demo `store` as a
  normal, deletable source.

## [0.3.3] - 2026-07-24

### Fixed

- First-run tutorial on a fresh (empty) workspace crashed with a `Catalog Error`:
  its "Run the example" button ran a hardcoded demo query (`FROM store.orders`)
  that only exists in the demo workspace. The example now adapts to the live
  catalog — the demo aggregation when the demo `store` source is present, a scan
  of your first real table otherwise, or a harmless `SELECT 42` when there are no
  sources yet.

## [0.3.2] - 2026-07-24

### Fixed

- `datacharter init` then `datacharter serve` failed with a `CharterError`: the
  scaffolded charter uses an empty `sources: {}`, which the loader wrongly
  rejected as "must be a non-empty mapping". A fresh workspace is now servable —
  add sources afterward via `charter.yaml` or the in-app source manager.

## [0.3.1] - 2026-07-24

### Changed

- Internal: extracted the origin/host request guard (DC-SEC-006) from the
  server into an importable `datacharter.server.security` module. No behavior
  change; the existing anti-DNS-rebinding / cross-origin protections are intact.

## [0.3.0] - 2026-07-24

### Added

- Agent view: a toggle on the results grid that masks the contract's PII columns
  in place, showing exactly what the agent and MCP server see (the model never
  sees raw PII) — right in the SQL editor, no LLM required.
- Source tree: collapsible `+`/`−` disclosure on every source and table, and
  expand a table to see its columns inline.
- Instant SQL preview: results update live a beat after you stop typing (row-capped,
  and errors stay silent until you press Run) — no Run click needed to see output.
- Chart captions: auto-detected charts (results) and agent-emitted charts (chat)
  now show a one-line plain-language caption of what they show — e.g. "bar of
  revenue by customer_id".
- `datacharter explain <sql>` — show a query's plan and row estimates without
  running it: a pre-flight cost check that surfaces per-source scans and what
  would push down.
- `datacharter sample <relation>` — print a PII-masked CSV sample of a relation
  (columns marked PII in the contract come back as `•••`), safe to paste into a
  bug ticket or share.
- Contract-scoped metrics: declare named `metrics:` in `charter.yaml` (a base
  relation + an aggregate expression + optional dimensions); `datacharter metric
  <name> [--by cols]` resolves each to one governed SELECT and runs it, so a
  certified `revenue` always means the same thing. Joins across sources and time
  grains are a later refinement.
- NL→SQL cache: when the agent answers via a query, its SQL is cached against a
  contract fingerprint; a repeat or normalized-reworded question re-runs the
  cached SQL on current data and skips the LLM round-trip (fresh data, no stale
  answers). Embedding-based semantic similarity is a follow-up.
- `datacharter serve --offline` — no-egress mode: the LLM agent is disabled (no
  data can reach any model endpoint) and connecting one at runtime is refused. It
  prints and writes a no-egress attestation to `.datacharter/attestation.json`.
- `datacharter snapshot <name> <sql>` and `datacharter recheck <name>` — save a
  query's result as `local.<name>` alongside its SQL, then later re-run it and
  diff against the saved result to answer "did this number change?". `recheck`
  exits non-zero when the result has changed.
- `datacharter drift` — report schema drift between the charter and the live
  sources: declared tables or PII columns that no longer exist. A missing PII
  column is a silent masking gap, so this is caught explicitly. Exits non-zero
  when drift is found, for use in CI.
- `datacharter scan` — introspect the configured sources and suggest PII columns
  for `charter.yaml`, both by column name and by sampled values (catches an
  email/SSN/IP column whose name gives nothing away). Turns "author a contract"
  into "review a generated one" for the PII map. Prints suggestions, or `--write`
  merges them into `charter.yaml` (round-trip; credential refs left untouched).
- `datacharter diff <left> <right>` and `Engine.diff` — a full-row set difference
  between two relations, across sources (postgres vs a file, prod vs staging, …)
  via the federation engine. Reports rows only in each side plus the common count,
  through the read-only guard. With `--key`, rows are matched by key and changed
  rows (same key, differing values) are counted separately.
- Per-query provenance: query results (API, agent tool results) now report the
  source relations and columns the query read — plus column lineage, mapping each
  output column to the input columns that feed it — parsed from the same AST the
  read-only guard uses. This is the trust signal for an agent answer: it shows
  which real columns an answer came from.
- `datacharter mcp` — an MCP (Model Context Protocol) server over stdio that
  exposes the four governed query tools (`list_sources`, `list_tables`,
  `describe_table`, `query`) to any MCP client. The read-only guard, PII masking,
  and credential scrubbing are inherited from the same toolbox the agent uses, so
  an external agent can explore your data without seeing raw PII or being able to
  write. Hand-rolled JSON-RPC 2.0, no new dependency.

### Changed

- Toolbar: **Snapshot** moved next to the query actions (away from the export
  format menu); hover tooltips on Run/Snapshot/Export/Explain.
- Demo workspace: bundled as one sqlite `store` contract holding `customers`
  and `orders`, so the sidebar reads contract → table → columns.

## [0.2.0] - 2026-07-24

### Added

- Sources view: add, edit, delete, and test-connection for data sources from the
  UI (toolbar toggle). Credentials are stored in the OS keyring; only `${NAME}`
  refs are written to `charter.yaml` (round-trip, comments preserved).
- Results grid shows a row-number column.
- Sidebar groups the catalog as system → source → tables (databases by engine,
  files by storage backend such as s3/gcs/azure).
- In-app Docs (About + FAQ) modal from the top bar.
- Resizable panels — drag the sidebar, chat, and editor/results boundaries; sizes
  persist across sessions.
- Day/night theme toggle in the top bar (defaults to day).
- The chat is disabled until an LLM is connected, and you can configure one from
  the chat panel (base URL / API key / model). The API key is stored in the OS
  keyring; base URL and model in a local file.

## [0.1.0] - 2026-07-23

First public release.

### Packaging

- Self-contained wheel: the web UI is bundled into the package, so
  `pip install datacharter` (or `uvx datacharter`) runs the full app with
  no Node toolchain and no repo checkout.

### Added

- Federation parity (D10): BigQuery and SQL Server via DuckDB community
  extensions; Snowflake via connector-extract fallback; uniform
  `source__table` compatibility views across every source; per-source
  filter/projection pushdown with EXPLAIN-verified tests.
- Connector pushdown planner (D11): deterministic, AST-driven filter +
  projection pushdown into the Snowflake extract — no agent required. Connector
  tables now materialize lazily with each query's pushdown applied and cached.
- Large-dataset handling (D12): connector extracts now report truncation via
  `QueryResult.warnings` (UI banner + agent), a per-source `max_rows:` cap in
  charter.yaml, and aggregation pushdown that runs single-table GROUP BY queries
  on the remote instead of extracting raw rows.
- Aggregation pushdown now also covers export and snapshots (D12): a pushable
  single-table aggregation is computed on the remote and its small result staged
  locally for `COPY`/snapshot, instead of raw-extracting (and capping) the table.
  Pushed `ORDER BY` emits explicit `NULLS FIRST`/`NULLS LAST` so the remote row
  order matches the local result deterministically.
- Virtualized results grid: only visible rows render to the DOM, so the grid
  scrolls a full 10k-row result smoothly (default visible cap raised 1k → 10k).
- `datacharter secrets set|list|rm` — manage `${NAME}` secrets in the OS keyring.

### Security

- Read-only guard rewritten on DuckDB's parser: counts and types statements and
  blocks filesystem/remote functions. Closes verified bypasses — dollar-quote
  statement stacking, `EXPLAIN ANALYZE COPY` file writes, CTE-prefixed DML, and
  arbitrary file reads via `read_csv`/`glob`/`postgres_scan`.
- HTTP surface hardened: Host-header allowlist (anti-DNS-rebinding) plus Origin
  and Sec-Fetch-Site checks reject cross-site browser requests.
- Local state DB is now encrypted (key from the OS keyring or
  `DATACHARTER_STATE_KEY`); connector literals escape backslash as well as quote;
  sync DB access is serialized; uploads are size-bounded and export temp files
  are cleaned up.

- Natural-language agent: `/api/agent/ask` SSE endpoint and chat panel.
  4-tool loop (list_sources/list_tables/describe_table/query) over any
  OpenAI-compatible endpoint via a dependency-free httpx client; charter
  PII columns masked in tool results; `serve --local` targets Ollama
  (qwen3:8b default). Agent can emit inline Vega-Lite charts.

- Local server: `datacharter serve` (localhost-only by default, port 8321)
  with JSON API (`/api/health|sources|tables|query|profile`), SSE query
  streaming with heartbeats, scrubbed error envelope, and ephemeral demo
  workspace when run without a charter.

- charter.yaml loader: `${NAME}` secret resolution (env → .env → OS
  keyring), hard error on credential literals with fix-it guidance,
  workspace portability lint (absolute/backslash paths), contextual
  error messages.
- Iceberg and Delta source types.
- `datacharter init`: workspace scaffolding (charter.yaml, queries/,
  .env.example, .gitignore) with optional generated demo dataset.
- Query engine core: DuckDB session bound to a workspace; postgres/mysql
  (temporary-secret + read-only attach), sqlite, csv/parquet/json sources
  (s3 paths supported); cross-source joins via native catalogs.
- Read-only SQL guard: statement allowlist with `local.*` DDL as the only
  write path; single-statement enforcement; comment-smuggling protection.
- Encrypted local persistence catalog (`local`) for snapshots.
- Spill hygiene: contained temp dir, always-on temp-file encryption,
  wipe on start/close, optional no-spill mode.
- Credential scrubbing on all engine error paths.
- Async query API with interrupt-based timeouts.
