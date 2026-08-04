# Changelog

All notable changes to this project will be documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- **The chat remembers the conversation.** Follow-up questions ("and which
  tier is biggest?") now carry the prior turns to LLM backends — including
  local models — bounded to what a small context window can hold. Clearing
  the chat clears the memory.

## [0.21.0] - 2026-08-04

### Added
- **Chat text is selectable and copyable.** Highlight any lines of an answer
  and copy them; every message also grows a hover ⧉ that copies it whole.
  Dragging selected text no longer triggers the file-drop overlay — that now
  appears only for actual files.
- **One click from dragged file to contract source.** Every upload in the
  sidebar has a "save as source" button: the file moves into the workspace,
  gets declared in charter.yaml, and any detected PII columns are written
  into the contract on the way — so a quick drag-drop can graduate into
  governed, committable data without retyping anything.

### Changed
- **The drag-and-drop upload cap is now 2 GB** (was 512 MB). Bigger files
  should still be added as sources — registered in place, no copy, no limit.

### Fixed
- **Dragged/uploaded files now have masking toggles** — and their PII columns
  are auto-detected the moment they land, so an uploaded CSV with an email
  column is masked from agents by default instead of slipping past the
  startup-only detection. Upload toggles persist via `local_access`.

## [0.20.0] - 2026-08-03

### Added
- **The Connect an LLM dialog now finds models already running on your
  machine.** Ollama, LM Studio, vLLM, and llama.cpp are probed (loopback
  only, silent when absent) and their loaded models listed under "Running on
  this machine" — one click connects, no API key, and if several runtimes or
  models are up you pick from the list. (`GET /api/llm/local`)
- **You can now disconnect and switch agents.** A connected agent (including
  Claude Code) has a disconnect button, and configuring an LLM while another
  backend is active actually switches to it — previously Claude Code was a
  dead end with no path back to a local or hosted model.

### Changed
- **Typo'd charter keys are now load errors.** An unknown key in a source,
  metric, or test body (e.g. `agent_acces:`) was silently ignored — governance
  that looked enabled while enforcing nothing. The error lists the allowed
  spellings.

### Reliability
- **Every release now gates on the built artifacts, not just unit tests.**
  A runtime smoke battery (timezone-aware fetch, uploads, contract writes,
  masking, snapshots, audit chain) runs against the frozen dmg/exe in desktop
  CI and against the built wheel before anything publishes to PyPI, and the
  bundle asserts its version and critical modules. This is the class of check
  that would have caught the 0.19.0 desktop pytz and About-box issues.

## [0.19.2] - 2026-08-03

### Fixed
- **Desktop: the pytz fix now actually reaches the frozen apps.** 0.19.1
  declared the dependency, but PyInstaller cannot trace DuckDB's dynamic
  import, so the dmg/exe still lacked it — pytz is now bundled explicitly.
  Timezone-aware parquet queries work in the desktop apps.
- **Desktop: the About box shows the real version** instead of 0.0.0
  (the bundle's Info.plist now carries the app version).
- **Error banners are copyable** — the live-preview error chip expands on
  click to the full message and its text is selectable.

## [0.19.1] - 2026-08-03

### Fixed
- **Querying parquet files with timezone-aware timestamp columns no longer
  fails with "No module named pytz"** — DuckDB's Python client needs pytz to
  materialize `TIMESTAMP WITH TIME ZONE` results, and it is now a declared
  dependency.

## [0.19.0] - 2026-08-03

### Added
- **Guides are now fully manageable in the browser** — create (+ New), edit,
  and delete, with a new `DELETE /api/guides/{name}` endpoint. Deleting a
  guide stops agents receiving it immediately.
- **Eval suites are now fully manageable in the browser** — a YAML editor in
  the Evals panel with create-from-template, save, and delete. Saving
  validates with the same checks `datacharter eval` uses, so a suite that
  saves, runs.
- **Data tests in the UI** — a "Run tests" card in the Evals panel runs the
  contract's `tests:` assertions and shows per-test verdicts.
- **Audit evidence export in the UI** — one button downloads the same
  self-contained pack as `datacharter audit export`.
- **Snapshot recheck in the UI** — every snapshot in the sidebar gains a
  recheck button that re-runs its query and reports inline whether the
  result changed.
- **Metrics in the command palette** — ⌘K now offers "Run metric: <name>"
  for every contract-defined metric, compiling it to SQL in the editor.

### Fixed
- **Snapshots created in the browser now persist their SQL**, so `datacharter
  recheck` (and the new recheck button) work on them — previously only
  CLI-created snapshots could be rechecked.

## [0.18.3] - 2026-08-02

### Fixed
- **Misplaced governance config is now a load error instead of silently
  ignored.** A top-level `row_filters:`/`agent_access:`/`pii:` block (they are
  source-level fields) previously did nothing while looking enabled — the
  loader now refuses with a message saying exactly where to move it. Agent
  access values must be booleans, so a YAML `deny` can no longer silently
  unmask a column.
- **A locked workspace now says so.** Opening a workspace another datacharter
  process is serving reported "the encryption key may have changed" and
  suggested deleting the state database; it now names the real cause.
- **`datacharter eval` refuses with a hint when no agent endpoint is
  configured** instead of reporting a misleading 0%, and endpoint errors
  (including `--judge`) print cleanly instead of a traceback.
- The demo workspace now exposes the `store__customers`-style flat views the
  quickstart teaches, and its `revenue` metric declares a `time_column` so
  `--grain` works out of the box.
- CLI errors that escape a subcommand print as one-line messages, and the
  `serve` banner is flushed so redirected logs aren't empty.

### Docs
- New Guides and Workbench (editor) pages; every page joined a unified nav
  with reading-order links; the landing page's charter example now uses real,
  loadable syntax; CLI reference gained `eval`, `audit`, `canary`, and
  `suggest`; MCP page gained per-client setup paths; clearer table-naming,
  drift, and offline-evals documentation throughout.

## [0.18.2] - 2026-08-02

### Fixed
- **Source- and table-level agent-access toggles now work on file sources**
  (CSV, Parquet, JSON, …). These register under the engine's `memory` database,
  so overrides keyed by the charter source name never reached them — the
  toggle wrote the contract but nothing changed. Both the catalog and the
  agent/MCP surface now honor them.
- **A source- or table-level toggle now clears the finer overrides beneath
  it.** Previously a stale field-level override silently won over a later
  table/source click — masking a table could leave a previously-unmasked PII
  column visible.
- **Desktop: exporting no longer risks quitting the app.** Downloads now go
  through the native save dialog instead of navigating the app window to the
  file (closing that "file" closed DataCharter).
- **Desktop: your theme and tour progress now survive relaunches** — the
  webview uses persistent storage and a stable server port, so the tour no
  longer reopens on every launch once dismissed.
- **Charts: all-numeric results now offer bar, line, and area** — previously
  only scatter was available unless a text or date column was present.
- **The tour's Agent-view step now runs a query that actually contains PII**,
  so flipping Agent view visibly masks a column instead of changing nothing.

### Changed
- **"Load the demo dataset" now seeds the full tour demo** on a fresh
  workspace — guides, evals, plain-english policies, canary tripwires, and a
  verifiable audit chain — so every panel has something real to show.
  Workspaces that already have sources still get just the demo data.

## [0.18.1] - 2026-08-01

### Changed
- Package metadata now credits the maker alongside the project: authors are
  DataCharter and Rishi Mashelkar.

### Removed
- An empty test file committed by accident in 0.18.0.

## [0.18.0] - 2026-08-01

### Added
- **Guided tour.** The in-app walkthrough grew from 5 steps to 11, adding the
  governance arc — the contract, seeing what an agent sees, guides, policies,
  the audit chain, and evals — with steps that open the panel they describe.
- **Tour workspace.** `datacharter serve` with no charter (and
  `datacharter init --demo --tour`) now scaffolds a workspace where every surface
  has real content: a guide, an eval suite, a policy (`aggregates only` ·
  `groups of at least 2`), canary tripwires, seeded query history for
  `datacharter suggest`, and a genuine hash-verifiable audit chain containing a
  real policy refusal. The plain `--demo` workspace stays minimal.

### Fixed
- **Claude Code was invisible in the desktop app.** A GUI-launched app inherits a
  minimal PATH, so the `claude` binary in `~/.local/bin` (or Homebrew, npm, bun,
  volta paths) was never found and the "Connect Claude Code" option stayed hidden.
  Detection now searches those locations and launches the resolved path.

## [0.17.0] - 2026-08-01

### Added
- **Plain-English policies, enforced.** A `policies:` block per relation —
  sentences (`aggregates only` · `groups of at least 10` · `no joins` ·
  `no joins to a, b`) or equivalent structured keys, compiled deterministically
  (unrecognized sentences are a load error). Enforced on the agent surface by
  DuckDB-parser analysis, fail-closed: aggregate-only certification (raw rows,
  DISTINCT, CTEs, set ops refused), k-anonymity group suppression (rewritten
  with a count guard computed after row-level security; suppressed groups noted
  in a result warning; strictest k wins), and queried-together join limits.
  `describe_table` surfaces a relation's policies so agents comply first try.
  The example workspace's `crm` table now ships policied.

### Fixed
- **Windows: the audit module crashed the server on import** (POSIX-only `fcntl`
  locking, shipped in 0.14.0/0.15.0) — file locking is now portable (`msvcrt` on
  Windows). Caught by the new desktop CI smoke matrix.

### Also added in 0.16.0
- **Self-writing guides.** `datacharter suggest` mines the workspace query
  history for repeated habits — recurring WHERE predicates per relation and
  tables that are always queried together — and turns them into guide
  suggestions with evidence counts. `--apply` appends them to
  `guides/suggested.md`; the Guides editor shows the same suggestions with
  one-click Add. Parsing is done by DuckDB itself (`json_serialize_sql`), so
  the whole loop is deterministic and offline. Suggestions dedupe against
  guides you have already written.
- `GET /api/guides/suggestions`.

## [0.16.0] - 2026-08-01

### Added
- **Desktop app (beta).** `datacharter-desktop` (new `[desktop]` extra) opens the
  governed explorer in a native window — workspace picker, remembered recents, and
  a `--smoke` flag for headless CI verification. Release artifacts: macOS `.dmg`
  (Apple Silicon + Intel) and Windows `.exe`, built by a CI matrix and attached to
  each release. Builds are unsigned for now (see the desktop docs for the macOS
  Sequoia "Open Anyway" walkthrough); Windows is CI-smoke-verified beta.

## [0.15.0] - 2026-08-01

### Added
- **Canary tripwires (opt-in).** `canary: on` plants `local.canaries` — synthetic
  PII embedding unique per-workspace tokens — masked by the same machinery that
  protects real data. A token appearing in any agent-bound result therefore proves
  the masking/guard layer failed: the hit is recorded as a tamper-evident `alarm`
  entry in the audit chain, and in block mode (default) the response is withheld;
  `canary: {mode: log}` alarms without blocking.
- `datacharter canary` (status + how to enable) and `datacharter canary drill`
  (pushes a synthetic hit through the real detection/alarm path).
- `GET /api/canary`; Audit panel gains a canary status chip (with explanatory
  tooltip) and a red alarm banner listing tripwire hits.

## [0.14.0] - 2026-08-01

### Added
- **Flight recorder: tamper-evident audit of agent data access.** Every tool call
  from every agent surface (chat, MCP clients, Claude Code) is recorded to an
  append-only, SHA-256 hash-chained log under `.datacharter/flight/` — dual
  attribution (OS user + MCP `clientInfo`/model), SQL, relations, masked columns,
  row counts, and a hash of the exact masked result. Metadata and hashes only;
  never raw rows. On by default; `audit: off` in `charter.yaml` disables.
- `datacharter audit` (recent sessions), `audit verify` (walks the chain; names
  the exact broken entry; nonzero exit), and `audit export` (evidence-pack zip:
  entries + verification statement + charter-in-force + summary).
- Server endpoints `GET /api/audit` and `GET /api/audit/verify`, and an **Audit**
  panel in the UI — session timeline with a live chain-verified badge.

## [0.13.0] - 2026-07-29

### Added
- **Eval LLM-judge.** `datacharter eval --judge` now scores freeform answers: for
  a case with an `expected_answer`, an LLM grades whether the agent's answer is
  consistent, folded into the case result alongside the deterministic assertions.
  Also available via the server eval-run endpoint.
- **`datacharter scan` flags literal PII in guides.** Since `guides/*.md` and
  per-table `context:` are served to agents, `scan` now reports literal emails,
  SSNs, cards, phones, and IPs found in that text (comment-stripped). `--strict`
  exits non-zero for CI.

## [0.12.0] - 2026-07-29

### Added
- **Agent evals.** Eval suites in `evals/*.yaml` score how well agents answer
  questions over your data. Assertions bind to the answer text, the SQL the agent
  ran, or the last query's scalar (`answer_contains`/`answer_matches`/
  `sql_contains`/`sql_excludes`/`result_scalar`). `datacharter eval` prints a
  scorecard; `--compare-guides` runs the suite with and without guides and
  reports the **lift**; `--threshold` gates CI; `--history` shows the trend and
  what regressed. Runs persist to a local `.datacharter/eval-runs/` ledger.
- **In-browser authoring.** `datacharter serve` gains an **Evals** panel (author,
  run, lift bar, trend, drilldown) and a **Guides** editor for `guides/*.md` and
  per-table context. Editing is restricted to a loopback server.
- New server endpoints: `GET/PUT /api/guides`, `GET /api/evals`,
  `POST /api/evals/run` (SSE), `GET /api/evals/history`.
- An eval suite in the `examples/ecommerce` template.

## [0.11.0] - 2026-07-29

### Added
- **Workspace guides — agent context in the contract.** Free-form markdown in
  `guides/*.md` (plus per-table `context:` mappings in `charter.yaml`) is served
  to the agent surface: the built-in chat agent's system prompt, the Claude Code
  driver, and every MCP client via the spec's `initialize` `instructions` field.
  `describe_table` gains a `context` key for tables with declared context. The
  human SQL editor is unaffected. `datacharter init` scaffolds a starter
  `guides/overview.md` (HTML comments in guides never reach the model).
- An end-to-end example workspace (`examples/ecommerce`) exercising PII masking,
  agent access, row filters, guides, tests, and a metric — copy it as a template.

## [0.10.4] - 2026-07-28

### Added
- MCP tools now carry annotations — a human-readable `title` plus `readOnlyHint`,
  `idempotentHint`, and `openWorldHint` — so MCP clients (and the Claude Connectors
  Directory) can display and reason about them. All four tools are read-only.
- Privacy Policy ([docs/privacy](https://datacharter.dev/privacy)):
  DataCharter collects no data, sends no telemetry, and runs entirely locally.

## [0.10.3] - 2026-07-28

### Changed
- Published DataCharter to the official [MCP Registry](https://registry.modelcontextprotocol.io).
  Added the required `mcp-name` ownership marker to the package README so the registry can verify
  the PyPI package. No functional or API changes.

## [0.10.2] - 2026-07-27

### Fixed
- Agent-access toggles now appear on **local snapshots** (`local.*`) in the left
  panel, and persist to a top-level `local_access` block in `charter.yaml`.
  Previously snapshots had no toggles and their access couldn't be adjusted (they
  were still masked by the PII default). The human editor is unaffected.

## [0.10.1] - 2026-07-27

### Fixed
- The app now serves a favicon (a theme-adaptive SVG mark), so browsers no longer
  log a `/favicon.ico` 404 on load.

## [0.10.0] - 2026-07-26

### Added
- Query history: explicit runs are recorded locally; a History panel (toolbar +
  ⌘K) reloads any past query. `datacharter lineage` aggregates history into a
  cross-source co-read + column-lineage graph.
- Rich profiling: the Profile tab now shows per-column top-value frequency bars
  (masked under Agent view for PII columns).
- Actionable agent transcript: each query the agent runs appears as a chip with
  "Open in editor".
- Connectors: `excel` (.xlsx) and `duckdb` (attach an existing .duckdb file).
- Cost pre-flight: an Estimate button (and `POST /api/explain`) shows the
  row-count estimate before you Run; warns on large scans.

## [0.9.0] - 2026-07-26

### Added
- `datacharter test`: declarative data assertions under a top-level `tests:`
  block (`not_null`, `unique`, `accepted_values`, `row_count`, `expression`),
  run through the read-only engine, exiting non-zero if any fail (for CI).
  `--select` runs one test.

## [0.8.0] - 2026-07-26

### Added
- Semantic layer: metrics can span tables via `joins` ({relation, on, type}) and
  declare a `time_column`, so `datacharter metric <name> --grain month` resolves
  to one governed SELECT grouped by a `date_trunc` (grain ∈ day/week/month/
  quarter/year). Metrics without joins/time_column are unchanged.

## [0.7.0] - 2026-07-26

### Added
- Command palette (⌘K / Ctrl-K): fuzzy-jump to any table or run any action
  (Run/Export/Snapshot/Profile/Explain, tab switch, toggle Agent view/theme,
  Help/tour, Open `<relation>`). ↑/↓ move, Enter runs, Esc closes.

## [0.6.0] - 2026-07-26

### Added
- Row-level security for the agent: `row_filters` in `charter.yaml` (table → SQL
  predicate) restrict the agent/MCP/Claude Code surfaces to matching rows via a
  fail-closed query rewrite; the human SQL editor is unaffected. Composes with
  `pii`/`agent_access` column masking. Static predicates (no per-user principal).

## [0.5.0] - 2026-07-26

Polish release (P2 tier): correctness, safety, and accessibility across CLI,
engine, and UI.

### Added
- `datacharter query "<sql>" [--format table|csv|json]`.
- `drift` detects column shape changes (new/removed/retyped) + new-PII rescan, with `--update` baseline.
- PII value-detection: Luhn cards + formatted phones (bare numeric IDs not flagged).
- Agent per-query statement-timeout budget.

### Fixed
- `PIVOT`/`UNPIVOT` run (they expand to CREATE+SELECT); CLI `snapshot` uses the pushed egress path.
- Keyboard-operable source tree; focus-trap/Escape/restore-focus on Help & Tutorial; reachable ✕.
- Editor-overwrite guard + confirm snapshot/upload delete.
- Honest truncation copy + non-destructive preview-error chip.
- Chat auto-scroll only near bottom; clear/copy; fenced code rendering.
- Typed connection/config status; defined `--muted` token.
- Claude Code driver: subprocess timeouts, stderr capture, persisted deny-list warm-start.

## [0.4.2] - 2026-07-26

### Added

- Concurrent reads: queries on local/attached (non-connector) workspaces run in
  parallel, each on its own cursor with its own timeout — a long query no longer
  freezes the live preview, the agent, or the catalog. (Snowflake stays
  serialized, since it materializes on read.)
- Snowflake sources accept an `authenticator` (SSO/MFA), and the connector is
  reused across queries instead of reconnecting each time.

### Fixed

- Background-action failures (export/snapshot/upload/access toggle) show a
  dismissible toast instead of blanking the results pane; the query error box is
  dismissible too.
- Profile/Explain tabs show a "Profiling…"/"Planning…" placeholder while loading.

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

- **Per-field agent-access toggles (left panel):** control per field / table / source whether
  the agent sees real values or masked (`•••`) ones, persisted to the contract
  (`agent_access:`). PII (declared or auto-detected) defaults to masked; everything else to
  real; an explicit toggle wins. Enforced on the agent surface only (agent, MCP, Claude Code);
  the human SQL editor is never masked.
- **Connect Claude Code:** run the chat agent on your local Claude Code subscription (no
  API key) instead of an OpenAI-wire LLM. Data stays governed — Claude reaches it only
  through datacharter's read-only, PII-masked tools (via a loopback `/api/tool` bridge) —
  and the connection is **refused (fail-closed) unless the tool sandbox verifies** it
  exposes nothing beyond those tools. Requires a Claude Pro/Max subscription + Claude Code
  installed.
- Empty workspaces get an "add your data" first-run launchpad (add a source / drop a
  CSV / load the demo dataset) instead of the demo feature-tour, which now auto-shows
  only when the workspace has sources. New `POST /api/demo` loads the demo `store` as a
  normal, deletable source.

### Added

- Remove snapshots and uploaded tables directly from the sidebar (a ✕ on `local.*` and
  uploaded rows), via `DELETE /api/snapshot/{name}` and `DELETE /api/uploads/{name}` —
  previously a saved snapshot could not be removed without wiping local state.

### Fixed

- The sidebar listed each attached-source table twice — once correctly and once as a fake
  "upload" — because the engine's internal `<source>__<table>` compatibility views were
  included in the catalog listing. They're now hidden.
- After uploading a CSV to an empty workspace, the explorer was unreachable: the upload
  registers a queryable table without a charter source, so the "no sources yet" launchpad
  stayed up. The launchpad now hides once there is anything to explore (a source *or* a
  table).
- Loading the demo again after deleting it failed (`table customers already exists`):
  deleting the source left `demo/store.db` on disk. `POST /api/demo` now recreates the
  demo tables idempotently.
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
