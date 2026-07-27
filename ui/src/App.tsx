import MonacoEditor from "@monaco-editor/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type QueryResult, type SourceInfo, type TableInfo } from "./api";
import ChartPanel from "./components/ChartPanel";
import ChatPanel from "./components/ChatPanel";
import QueryFiles from "./components/QueryFiles";
import ResultsGrid from "./components/ResultsGrid";
import SourceTree from "./components/SourceTree";
import SourcesView from "./components/SourcesView";
import HelpModal from "./components/HelpModal";
import EmptyState from "./components/EmptyState";
import Toast from "./components/Toast";
import CommandPalette from "./components/CommandPalette";
import HistoryPanel from "./components/HistoryPanel";
import ProfileBars from "./components/ProfileBars";
import { type Command } from "./lib/commandPalette";
import { shouldReplaceEditor } from "./lib/editorGuard";
import { formatEstimate } from "./lib/estimate";
import { exportRequest } from "./lib/mask";
import { useResize } from "./lib/useResize";
import Tutorial, { hasSeenTutorial } from "./components/Tutorial";
import { registerCompletions } from "./monaco";
import { STARTER, exampleFor, shouldShowLaunchpad, shouldShowTour } from "./onboarding";

type Tab = "results" | "chart" | "profile" | "plan";

export default function App() {
  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [tables, setTables] = useState<TableInfo[]>([]);
  const [sql, setSql] = useState(STARTER);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [profileResult, setProfileResult] = useState<QueryResult | null>(null);
  const [error, setError] = useState<string | null>(null); // query errors: replace the grid
  const [actionError, setActionError] = useState<string | null>(null); // background actions: toast
  const [previewError, setPreviewError] = useState<string | null>(null); // live-preview parse error
  const [running, setRunning] = useState(false);
  const [tab, setTab] = useState<Tab>("results");
  const [agentView, setAgentView] = useState(false);
  const [exportFormat, setExportFormat] = useState("csv");
  const [planText, setPlanText] = useState<string | null>(null);
  const [profileLoading, setProfileLoading] = useState(false);
  const [planLoading, setPlanLoading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [showTutorial, setShowTutorial] = useState(false);
  const [catalogLoaded, setCatalogLoaded] = useState(false);
  const [view, setView] = useState<"explorer" | "sources">("explorer");
  const [showHelp, setShowHelp] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [estimate, setEstimate] = useState<number | null | undefined>(undefined);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark">(
    () => (localStorage.getItem("dc-theme") as "light" | "dark") || "light",
  );
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("dc-theme", theme);
  }, [theme]);
  const dark = theme === "dark";
  // PII columns declared across all sources — masked in "Agent view" (what a model sees).
  // What the agent sees masked: the effective agent-access map (declared PII, auto-detected,
  // and any field/table/source toggles) — so "Agent view" mirrors the toggles, not just PII.
  const maskedColumns = useMemo(() => {
    const set = new Set<string>();
    for (const t of tables)
      for (const [col, a] of Object.entries(t.access ?? {})) if (a.masked) set.add(col.toLowerCase());
    return set;
  }, [tables]);
  const sidebarW = useResize("dc-sidebar-w", 260, "x", false, 160);
  const chatW = useResize("dc-chat-w", 340, "x", true, 240);
  const editorH = useResize("dc-editor-h", 300, "y", false, 120);
  const sqlRef = useRef(sql);
  sqlRef.current = sql;
  const lastLoadedRef = useRef(sql); // last value WE put in the editor (for dirty detection)
  const loadSql = useCallback((text: string) => {
    setSql(text);
    lastLoadedRef.current = text;
  }, []);
  const tablesRef = useRef(tables);
  tablesRef.current = tables;
  const resultRef = useRef(result);
  resultRef.current = result;

  const refreshCatalog = useCallback(() => {
    Promise.allSettled([
      api.sources().then((b) => setSources(b.sources)),
      api.tables().then((b) => setTables(b.tables)),
    ]).finally(() => setCatalogLoaded(true));
  }, []);

  useEffect(refreshCatalog, [refreshCatalog]);

  // Auto-show the guided tour only on a populated workspace; empty ones get the launchpad.
  useEffect(() => {
    if (shouldShowTour(hasSeenTutorial(), sources.length, catalogLoaded)) setShowTutorial(true);
  }, [catalogLoaded, sources.length]);

  const run = useCallback(
    async (sqlText?: string) => {
      setRunning(true);
      setError(null);
      setProfileResult(null);
      try {
        setResult(await api.query(sqlText ?? sqlRef.current, 10000, true));
        setTab("results");
        refreshCatalog();
      } catch (e) {
        setResult(null);
        setError((e as Error).message);
      } finally {
        setRunning(false);
      }
    },
    [refreshCatalog],
  );

  const loadAndRunExample = useCallback(() => {
    const example = exampleFor(tablesRef.current);
    loadSql(example);
    run(example);
  }, [run, loadSql]);

  // Instant preview: a beat after you stop typing, auto-run the query (row-capped,
  // silent on error) so results update live without pressing Run.
  useEffect(() => {
    setEstimate(undefined); // a prior estimate no longer matches the edited query
    const body = sql.replace(/--[^\n]*/g, "").trim();
    if (!body) return;
    const timer = setTimeout(() => {
      api
        .query(sql, 200)
        .then((preview) => {
          setResult(preview);
          setError(null);
          setPreviewError(null);
        })
        .catch((e) => setPreviewError((e as Error).message));
    }, 700);
    return () => clearTimeout(timer);
  }, [sql]);

  const profile = useCallback(async () => {
    setTab("profile");
    if (profileResult) return;
    setProfileLoading(true);
    try {
      const body = sqlRef.current.trim().replace(/;\s*$/, "");
      setProfileResult(await api.profile(body));
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setProfileLoading(false);
    }
  }, [profileResult]);

  const estimateCost = useCallback(async () => {
    try {
      const r = await api.explain(sqlRef.current);
      setEstimate(r.estimated_rows);
    } catch (e) {
      setActionError((e as Error).message);
    }
  }, []);

  const snapshot = useCallback(async () => {
    const name = window.prompt("Snapshot as local.<name>", "snap");
    if (!name) return;
    const resp = await fetch("/api/snapshot", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ sql: sqlRef.current, name }),
    });
    if (resp.ok) refreshCatalog();
    else setActionError((await resp.json()).error?.message ?? "Snapshot failed");
  }, [refreshCatalog]);

  const exportResult = useCallback(async () => {
    const { body, filename } = exportRequest(
      sqlRef.current,
      exportFormat,
      agentView,
      maskedColumns,
      resultRef.current?.columns ?? [],
    );
    const resp = await fetch("/api/export", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!resp.ok) {
      setActionError((await resp.json()).error?.message ?? "Export failed");
      return;
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }, [exportFormat, agentView, maskedColumns]);

  const pickRelation = useCallback(
    (relation: string) => {
      const next = `SELECT * FROM ${relation} LIMIT 100;`;
      if (
        shouldReplaceEditor(sqlRef.current, lastLoadedRef.current) ||
        window.confirm("Replace your current query with a SELECT for this table?")
      ) {
        loadSql(next);
      }
    },
    [loadSql],
  );

  const explain = useCallback(async () => {
    setTab("plan");
    setPlanLoading(true);
    try {
      const body = sqlRef.current.trim().replace(/;\s*$/, "");
      const res = await api.query(`EXPLAIN ANALYZE ${body}`);
      setPlanText(res.rows.map((r) => r.join("\n")).join("\n"));
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setPlanLoading(false);
    }
  }, []);

  const uploadFile = useCallback(
    async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      const resp = await fetch("/api/upload", { method: "POST", body: form });
      const body = await resp.json();
      if (!resp.ok) {
        setActionError(body.error?.message ?? "Upload failed");
        return;
      }
      loadSql(`SELECT * FROM ${body.table} LIMIT 100;`);
      refreshCatalog();
    },
    [refreshCatalog],
  );

  const loadDemo = useCallback(async () => {
    await api.loadDemo();
    refreshCatalog();
  }, [refreshCatalog]);

  const removeObject = useCallback(
    async (kind: "snapshot" | "upload", name: string) => {
      const label = kind === "snapshot" ? `snapshot local.${name}` : `uploaded table ${name}`;
      if (!window.confirm(`Remove ${label}? This can't be undone.`)) return;
      try {
        await (kind === "snapshot" ? api.deleteSnapshot(name) : api.deleteUpload(name));
        refreshCatalog();
      } catch (e) {
        setActionError((e as Error).message);
      }
    },
    [refreshCatalog],
  );

  const setAccess = useCallback(
    async (a: { source: string; table?: string; column?: string; value: boolean }) => {
      try {
        await api.setAgentAccess(a);
        refreshCatalog();
      } catch (e) {
        setActionError((e as Error).message);
      }
    },
    [refreshCatalog],
  );

  const onDrop = useCallback(
    async (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      for (const file of Array.from(e.dataTransfer.files)) await uploadFile(file);
    },
    [uploadFile],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const commands = useMemo<Command[]>(() => {
    const a = (id: string, label: string, run: () => void): Command => ({ id, label, run });
    const actions = [
      a("run", "Run query", () => run()),
      a("export", "Export result", () => exportResult()),
      a("snapshot", "Snapshot result", () => snapshot()),
      a("profile", "Profile", () => profile()),
      a("explain", "Explain plan", () => explain()),
      a("estimate", "Estimate cost", () => estimateCost()),
      a("history", "Query history", () => setShowHistory(true)),
      a("tab-results", "Go to Results", () => setTab("results")),
      a("tab-chart", "Go to Chart", () => setTab("chart")),
      a("tab-plan", "Go to Plan", () => setTab("plan")),
      a("agent-view", "Toggle Agent view", () => setAgentView((v) => !v)),
      a("theme", "Toggle theme", () => setTheme((t) => (t === "dark" ? "light" : "dark"))),
      a("help", "Help — About & FAQ", () => setShowHelp(true)),
      a("tour", "Take the tour", () => setShowTutorial(true)),
    ];
    const tableCmds = tables.map((t) => {
      const rel = t.source === "memory" ? t.table : `${t.source}.${t.table}`;
      return a(`open:${rel}`, `Open ${rel}`, () => pickRelation(rel));
    });
    return [...actions, ...tableCmds];
  }, [run, exportResult, snapshot, profile, explain, estimateCost, pickRelation, tables]);

  return (
    <div
      className={dragging ? "app dragging" : "app"}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={(e) => {
        if (e.currentTarget === e.target) setDragging(false);
      }}
      onDrop={onDrop}
    >
      {dragging && <div className="drop-overlay">Drop csv / parquet / json to query it</div>}
      {showTutorial && (
        <Tutorial
          actions={{
            loadAndRunExample,
            showChart: () => setTab("chart"),
            showProfile: profile,
          }}
          onClose={() => setShowTutorial(false)}
        />
      )}
      {showHelp && <HelpModal onClose={() => setShowHelp(false)} />}
      {showHistory && (
        <HistoryPanel onPick={(s) => loadSql(s)} onClose={() => setShowHistory(false)} />
      )}
      {actionError && <Toast message={actionError} onClose={() => setActionError(null)} />}
      {paletteOpen && (
        <CommandPalette commands={commands} onClose={() => setPaletteOpen(false)} />
      )}
      <header className="topbar">
        <svg className="logo" viewBox="0 0 128 128" aria-hidden="true">
          <circle cx="64" cy="64" r="56" fill="none" stroke="currentColor" strokeWidth="7" />
          <path
            d="M30 84 L52 60 L66 72 L92 42"
            fill="none"
            stroke="#3B82C4"
            strokeWidth="11"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <path
            d="M78 38 L96 38 L96 56"
            fill="none"
            stroke="#3B82C4"
            strokeWidth="11"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <span className="name">DataCharter</span>
        <span className="tagline">charter your data</span>
        <span className="spacer" />
        <button
          className="topbar-btn"
          onClick={() => setTheme(dark ? "light" : "dark")}
          title={dark ? "Switch to day" : "Switch to night"}
        >
          {dark ? "☀" : "🌙"}
        </button>
        <button
          className="topbar-btn"
          onClick={() => setShowHistory(true)}
          title="Query history"
        >
          History
        </button>
        <button className="topbar-btn" onClick={() => setShowHelp(true)} title="About & FAQ">
          Docs
        </button>
        <button
          className="topbar-btn"
          onClick={() => setView(view === "sources" ? "explorer" : "sources")}
          title="Manage data sources"
        >
          {view === "sources" ? "Explorer" : "Sources"}
        </button>
        <button
          className="help-btn"
          onClick={() => setShowTutorial(true)}
          title="Getting started"
          aria-label="Getting started"
        >
          ?
        </button>
      </header>
      <div className="layout">
        <aside className="sidebar" style={{ width: sidebarW.size }}>
          <SourceTree
            sources={sources}
            tables={tables}
            onPick={pickRelation}
            onRemove={removeObject}
            onSetAccess={setAccess}
          />
        </aside>
        <div className="resizer-x" onMouseDown={sidebarW.onMouseDown} />
        <main className="main">
          {view === "sources" ? (
            <SourcesView onChange={refreshCatalog} />
          ) : shouldShowLaunchpad(catalogLoaded, sources.length, tables.length) ? (
            <EmptyState
              onAddSource={() => setView("sources")}
              onUpload={uploadFile}
              onLoadDemo={loadDemo}
            />
          ) : (
          <>
          <section className="editor-pane" style={{ height: editorH.size }}>
            <div className="toolbar">
              <button
                className="primary"
                onClick={() => run()}
                disabled={running}
                title="Run the query (⌘/Ctrl+Enter)"
              >
                {running ? "Running…" : "Run"}
              </button>
              <QueryFiles currentSql={() => sqlRef.current} onLoad={loadSql} />
              <button
                onClick={snapshot}
                title="Save this result as a reusable local.<name> table"
              >
                Snapshot
              </button>
              <span className="spacer" />
              <select
                value={exportFormat}
                onChange={(e) => setExportFormat(e.target.value)}
                title="Export format (CSV, Parquet, JSON, XLSX)"
              >
                {["csv", "parquet", "json", "xlsx"].map((f) => (
                  <option key={f}>{f}</option>
                ))}
              </select>
              <button
                onClick={exportResult}
                title={
                  agentView
                    ? "Download the masked Agent-view result (PII → •••)"
                    : "Download the result in the selected format"
                }
              >
                Export{agentView ? " (masked)" : ""}
              </button>
              <button onClick={explain} title="Show the query plan (EXPLAIN ANALYZE)">
                Explain
              </button>
              <button onClick={estimateCost} title="Estimate rows this query will return (pre-flight)">
                Estimate
              </button>
              {estimate !== undefined && (
                <span
                  className={
                    formatEstimate(estimate).warn ? "estimate-badge warn" : "estimate-badge"
                  }
                >
                  {formatEstimate(estimate).label}
                </span>
              )}
            </div>
            <MonacoEditor
              language="sql"
              theme={dark ? "vs-dark" : "vs"}
              value={sql}
              onChange={(v) => setSql(v ?? "")}
              onMount={(editor, monaco) => {
                editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => run());
                registerCompletions(monaco, () => tablesRef.current);
              }}
              options={{
                minimap: { enabled: false },
                fontSize: 13,
                scrollBeyondLastLine: false,
                automaticLayout: true,
              }}
            />
          </section>
          <div className="resizer-y" onMouseDown={editorH.onMouseDown} />
          <section className="results-pane">
            <div className="tabs">
              <button
                className={tab === "results" ? "tab active" : "tab"}
                onClick={() => setTab("results")}
              >
                Results
              </button>
              <button
                className={tab === "chart" ? "tab active" : "tab"}
                onClick={() => setTab("chart")}
                disabled={!result}
              >
                Chart
              </button>
              <button className={tab === "profile" ? "tab active" : "tab"} onClick={profile}>
                Profile
              </button>
              <button
                className={tab === "plan" ? "tab active" : "tab"}
                onClick={() => setTab("plan")}
                disabled={!planText}
              >
                Plan
              </button>
              <label
                className="agent-view-toggle"
                title="Show what the agent and MCP server see — PII columns masked"
              >
                <input
                  type="checkbox"
                  checked={agentView}
                  onChange={(e) => setAgentView(e.target.checked)}
                />
                Agent view
              </label>
            </div>
            {previewError && !error && (
              <div className="preview-error" title={previewError}>
                ⚠ live preview: {previewError.split("\n")[0]}
              </div>
            )}
            <div className="tab-body">
              {error && (
                <div className="error-box">
                  <span>{error}</span>
                  <button
                    className="error-close"
                    aria-label="Dismiss"
                    onClick={() => setError(null)}
                  >
                    ×
                  </button>
                </div>
              )}
              {!error && tab === "results" && result && (
                <ResultsGrid result={result} maskColumns={agentView ? maskedColumns : undefined} />
              )}
              {!error && tab === "chart" && result && (
                <ChartPanel
                  result={result}
                  dark={dark}
                  maskColumns={agentView ? maskedColumns : undefined}
                />
              )}
              {!error && tab === "profile" &&
                (profileResult ? (
                  <div className="profile-scroll">
                    <ResultsGrid result={profileResult} />
                    {profileResult.top_values && (
                      <ProfileBars
                        top={profileResult.top_values}
                        masked={agentView ? maskedColumns : undefined}
                      />
                    )}
                  </div>
                ) : profileLoading ? (
                  <div className="empty-state">Profiling…</div>
                ) : null)}
              {!error && tab === "plan" &&
                (planText ? (
                  <pre className="plan">{planText}</pre>
                ) : planLoading ? (
                  <div className="empty-state">Planning…</div>
                ) : null)}
              {!error && !result && tab !== "profile" && (
                <div className="empty-state">Run a query to see results.</div>
              )}
            </div>
          </section>
          </>
          )}
        </main>
        <div className="resizer-x" onMouseDown={chatW.onMouseDown} />
        <aside className="chat-dock" style={{ width: chatW.size }}>
          <ChatPanel dark={dark} onOpenSql={loadSql} />
        </aside>
      </div>
    </div>
  );
}
