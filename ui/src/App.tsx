import MonacoEditor from "@monaco-editor/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type QueryResult, type SourceInfo, type TableInfo } from "./api";
import ChartPanel from "./components/ChartPanel";
import ChatPanel from "./components/ChatPanel";
import QueryFiles from "./components/QueryFiles";
import QueryTabs from "./components/QueryTabs";
import ResultsGrid from "./components/ResultsGrid";
import CharterStudio from "./components/CharterStudio";
import SourceTree from "./components/SourceTree";
import SourcesView from "./components/SourcesView";
import AuditView from "./components/AuditView";
import EvalsView from "./components/EvalsView";
import GuidesEditor from "./components/GuidesEditor";
import HelpModal from "./components/HelpModal";
import EmptyState from "./components/EmptyState";
import Toast from "./components/Toast";
import { uploadNotice } from "./lib/uploadNotice";
import { makeEpoch, shouldPreview } from "./lib/queryLifecycle";
import CommandPalette from "./components/CommandPalette";
import HistoryPanel from "./components/HistoryPanel";
import ProfileBars from "./components/ProfileBars";
import { buildPaletteCommands } from "./lib/paletteCommands";
import { shouldReplaceEditor } from "./lib/editorGuard";
import { formatEstimate } from "./lib/estimate";
import { exportRequest } from "./lib/mask";
import { decodeQueryHash, encodeQueryHash } from "./lib/queryHash";
import { resultToMarkdown } from "./lib/resultMarkdown";
import { useResize } from "./lib/useResize";
import Tutorial, { hasSeenTutorial } from "./components/Tutorial";
import { registerCompletions } from "./monaco";
import { STARTER, agentExampleFor, exampleFor, shouldShowLaunchpad, shouldShowTour } from "./onboarding";

type Tab = "results" | "chart" | "profile" | "plan" | "sql";
type Door = "explore" | "ask" | "govern";
type GovernPage = "sources" | "evals" | "guides" | "audit" | "studio";
type QueryBuf = {
  id: string;
  title: string;
  sql: string;
  result: QueryResult | null;
  error: string | null;
  offset: number;
};

const PAGE_ROWS = 10000;

export default function App() {
  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [tables, setTables] = useState<TableInfo[]>([]);
  const [metrics, setMetrics] = useState<
    { name: string; sql: string; dimensions: string[]; has_time: boolean }[]
  >([]);
  const [sql, setSql] = useState(STARTER);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [profileResult, setProfileResult] = useState<QueryResult | null>(null);
  const [error, setError] = useState<string | null>(null); // query errors: replace the grid
  const [actionError, setActionError] = useState<string | null>(null); // background actions: toast
  const [notice, setNotice] = useState<string | null>(null); // governance notices: info toast
  // Degraded-but-running states (unencrypted state DB, dead recorder, unplanted
  // canary) — each shipped as a SILENT failure once; now they get a banner.
  const [degraded, setDegraded] = useState<string[]>([]);
  const [previewError, setPreviewError] = useState<string | null>(null); // live-preview parse error
  const [previewExpanded, setPreviewExpanded] = useState(false);
  const [running, setRunning] = useState(false);
  const [offset, setOffset] = useState(0);
  const [queryTabs, setQueryTabs] = useState<QueryBuf[]>(() => [
    { id: "1", title: "Query 1", sql: STARTER, result: null, error: null, offset: 0 },
  ]);
  const [activeTabId, setActiveTabId] = useState("1");
  const [savedQueries, setSavedQueries] = useState<string[]>([]);
  const [connectTick, setConnectTick] = useState(0);
  const fileRef = useRef<HTMLInputElement>(null);
  const [tab, setTab] = useState<Tab>("results");
  const [agentView, setAgentView] = useState(false);
  // The TRUE agent view: the current SQL re-run through the governed tool
  // surface (masking + policies + row filters), or the refusal it would get.
  const [agentResult, setAgentResult] = useState<QueryResult | null>(null);
  const [agentRefusal, setAgentRefusal] = useState<string | null>(null);
  const [exportFormat, setExportFormat] = useState("csv");
  const [planText, setPlanText] = useState<string | null>(null);
  const [profileLoading, setProfileLoading] = useState(false);
  const [planLoading, setPlanLoading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [showTutorial, setShowTutorial] = useState(false);
  const [catalogLoaded, setCatalogLoaded] = useState(false);
  const [view, setView] = useState<"explorer" | GovernPage>("explorer");
  const [door, setDoor] = useState<Door>("explore");
  const openGovern = (page: GovernPage) => {
    setDoor("govern");
    setView(page);
  };
  const openExplore = () => {
    setDoor("explore");
    setView("explorer");
  };
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
  const activeTabIdRef = useRef(activeTabId);
  activeTabIdRef.current = activeTabId;
  const offsetRef = useRef(offset);
  offsetRef.current = offset;
  const errorRef = useRef(error);
  errorRef.current = error;
  const abortRef = useRef<AbortController | null>(null);
  // Sequencing for the two result producers (live preview vs. explicit Run) so a
  // late preview response can't clobber a full Run result. See queryLifecycle.
  const epoch = useRef(makeEpoch()).current;
  const previewTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const lastRunSqlRef = useRef<string | null>(null);
  const runningRef = useRef(running);
  runningRef.current = running;

  // When Agent view is on, run the current SQL through the governed tool
  // surface so the grid shows EXACTLY what the agent receives — including a
  // policy refusal or row-filtered rows, not just client-side column masking.
  useEffect(() => {
    if (!agentView || !result) {
      setAgentResult(null);
      setAgentRefusal(null);
      return;
    }
    let cancelled = false;
    setAgentResult(null);
    setAgentRefusal(null);
    api
      .runToolQuery(sqlRef.current)
      .then(({ result: text }) => {
        if (cancelled) return;
        if (text.startsWith("Error:")) {
          setAgentRefusal(text.replace(/^Error:\s*/, ""));
        } else {
          try {
            setAgentResult(JSON.parse(text) as QueryResult);
          } catch {
            setAgentRefusal("Could not parse the agent result.");
          }
        }
      })
      .catch((e) => !cancelled && setAgentRefusal((e as Error).message));
    return () => {
      cancelled = true;
    };
  }, [agentView, result]);

  const refreshCatalog = useCallback(() => {
    Promise.allSettled([
      api.sources().then((b) => setSources(b.sources)),
      api.tables().then((b) => setTables(b.tables)),
      api.listMetrics().then((b) => setMetrics(b.metrics)),
      api.listQueries().then((b) => setSavedQueries(b.queries)),
    ]).finally(() => setCatalogLoaded(true));
  }, []);

  useEffect(refreshCatalog, [refreshCatalog]);

  useEffect(() => {
    const sqlFromLink = decodeQueryHash(window.location.hash);
    if (!sqlFromLink) return;
    loadSql(sqlFromLink);
    history.replaceState(null, "", window.location.pathname + window.location.search);
  }, [loadSql]);

  useEffect(() => {
    void api.health().then((h) => {
      const warns: string[] = [];
      if (h.state_encrypted === false)
        warns.push(
          "Local state DB is UNENCRYPTED (no OS keyring available). Set DATACHARTER_STATE_KEY to encrypt snapshots at rest.",
        );
      if (h.audit_recording === false)
        warns.push("Audit recorder failed — agent access is NOT being recorded. Check the server log.");
      if (h.canary_planted === false)
        warns.push("Canary tripwires are DEGRADED — planting local.canaries failed. See the Audit view.");
      setDegraded(warns);
    });
  }, []);

  // Auto-show the guided tour only on a populated workspace; empty ones get the launchpad.
  useEffect(() => {
    if (shouldShowTour(hasSeenTutorial(), sources.length, catalogLoaded)) setShowTutorial(true);
  }, [catalogLoaded, sources.length]);

  const run = useCallback(
    async (sqlText?: string, pageOffset = 0) => {
      const text = sqlText ?? sqlRef.current;
      const tabId = activeTabIdRef.current;
      clearTimeout(previewTimer.current); // cancel any pending preview…
      abortRef.current?.abort();
      const ac = new AbortController();
      abortRef.current = ac;
      const token = epoch.next(); // …and invalidate any preview already in flight
      lastRunSqlRef.current = text;
      setRunning(true);
      setError(null);
      setProfileResult(null);
      try {
        const res = await api.query(text, PAGE_ROWS, pageOffset === 0, {
          offset: pageOffset,
          signal: ac.signal,
        });
        if (!epoch.isCurrent(token)) return; // a newer run/preview superseded us
        setQueryTabs((tabs) =>
          tabs.map((t) =>
            t.id === tabId
              ? { ...t, sql: text, result: res, error: null, offset: pageOffset }
              : t,
          ),
        );
        if (activeTabIdRef.current === tabId) {
          setResult(res);
          setTab("results");
          setOffset(pageOffset);
        }
        refreshCatalog();
      } catch (e) {
        if (!epoch.isCurrent(token)) return;
        if ((e as Error).name === "AbortError") return;
        if ((e as { kind?: string }).kind === "query_cancelled") return;
        const msg = (e as Error).message;
        setQueryTabs((tabs) =>
          tabs.map((t) => (t.id === tabId ? { ...t, error: msg, result: null } : t)),
        );
        if (activeTabIdRef.current === tabId) {
          setResult(null);
          setError(msg);
        }
      } finally {
        if (epoch.isCurrent(token)) setRunning(false);
      }
    },
    [refreshCatalog, epoch],
  );

  const cancelRun = useCallback(async () => {
    abortRef.current?.abort();
    epoch.next();
    setRunning(false);
    try {
      await api.cancelQuery();
    } catch {
      /* nothing in flight is fine */
    }
  }, [epoch]);

  const snapshotActive = (): QueryBuf[] =>
    queryTabs.map((t) =>
      t.id === activeTabId
        ? { ...t, sql, result, error, offset }
        : t,
    );

  const applyTab = (next: QueryBuf) => {
    setActiveTabId(next.id);
    setSql(next.sql);
    setResult(next.result);
    setError(next.error);
    setOffset(next.offset);
    lastLoadedRef.current = next.sql;
  };

  const selectQueryTab = (id: string) => {
    if (id === activeTabId) return;
    const saved = snapshotActive();
    const next = saved.find((t) => t.id === id);
    if (!next) return;
    setQueryTabs(saved);
    applyTab(next);
  };

  const newQueryTab = () => {
    const saved = snapshotActive();
    const buf: QueryBuf = {
      id: `q${Date.now()}`,
      title: `Query ${saved.length + 1}`,
      sql: STARTER,
      result: null,
      error: null,
      offset: 0,
    };
    setQueryTabs([...saved, buf]);
    applyTab(buf);
  };

  const closeQueryTab = (id: string) => {
    if (queryTabs.length === 1) return;
    const saved = snapshotActive();
    const idx = saved.findIndex((t) => t.id === id);
    const nextTabs = saved.filter((t) => t.id !== id);
    const next = nextTabs[Math.max(0, idx - 1)] ?? nextTabs[0];
    setQueryTabs(nextTabs);
    applyTab(next);
  };

  const loadAndRunExample = useCallback(() => {
    const example = exampleFor(tablesRef.current);
    loadSql(example);
    run(example);
  }, [run, loadSql]);

  // Tour's Agent-view step: run a query that actually has masked columns, then
  // show the agent surface — toggling on a PII-free result demonstrates nothing.
  const runAgentExample = useCallback(() => {
    const example = agentExampleFor(tablesRef.current);
    if (example) {
      loadSql(example);
      run(example);
    }
    setAgentView(true);
  }, [run, loadSql]);

  // Instant preview: a beat after you stop typing, auto-run the query (row-capped,
  // silent on error) so results update live without pressing Run. Skipped while a
  // Run is in flight or when the SQL matches what Run just executed, and each
  // response is dropped unless it is still the newest request (see queryLifecycle).
  useEffect(() => {
    setEstimate(undefined); // a prior estimate no longer matches the edited query
    if (!shouldPreview(sql, lastRunSqlRef.current, runningRef.current)) return;
    const timer = setTimeout(() => {
      const token = epoch.next();
      api
        .query(sql, 200)
        .then((preview) => {
          if (!epoch.isCurrent(token)) return; // a Run or newer preview won
          setResult(preview);
          setError(null);
          setPreviewError(null);
        })
        .catch((e) => epoch.isCurrent(token) && setPreviewError((e as Error).message));
    }, 700);
    previewTimer.current = timer;
    return () => clearTimeout(timer);
  }, [sql, epoch]);

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

  const exportResult = useCallback(async (formatOverride?: string) => {
    const format = formatOverride ?? exportFormat;
    if (formatOverride) setExportFormat(formatOverride);
    const { body, filename } = exportRequest(
      sqlRef.current,
      format,
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
        run(next);
      }
    },
    [loadSql, run],
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
      const preview = `SELECT * FROM ${body.table} LIMIT 100;`;
      loadSql(preview);
      run(preview);
      refreshCatalog();
      // A detection FAILURE (columns left unmasked) must be loud — surface it as
      // an error, not the friendly governance notice.
      if (body.warning) setActionError(body.warning);
      const n = uploadNotice(body.table, body.pii ?? []);
      if (n) setNotice(n);
    },
    [refreshCatalog, loadSql, run],
  );

  const loadDemo = useCallback(async () => {
    await api.loadDemo();
    refreshCatalog();
  }, [refreshCatalog]);

  const charterFiles = useCallback(async () => {
    const body = await api.charterFromFiles();
    refreshCatalog();
    if (body.added.length === 0) {
      setNotice(
        body.skipped.length
          ? "Those files are already in the charter."
          : "No csv, parquet, json, or xlsx files in this folder.",
      );
      return;
    }
    const first = body.added[0];
    const preview = `SELECT * FROM ${first.name} LIMIT 100;`;
    loadSql(preview);
    run(preview);
    const pii = Object.entries(body.pii)
      .filter(([, cols]) => cols.length)
      .map(([n, cols]) => `${n}: ${cols.join(", ")}`)
      .join("; ");
    setNotice(
      `Chartered ${body.added.length} file(s).${pii ? ` PII flagged (${pii}). Review charter.yaml.` : " Review charter.yaml."}`,
    );
  }, [refreshCatalog, loadSql, run]);

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
      if (e.key === "Escape" && runningRef.current) {
        e.preventDefault();
        void cancelRun();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [cancelRun]);

  const saveQueryFile = useCallback(async () => {
    const name = window.prompt("Save as queries/<name>.sql", "query");
    if (!name) return;
    try {
      await api.saveQuery(name, sqlRef.current);
      refreshCatalog();
    } catch (e) {
      setActionError((e as Error).message);
    }
  }, [refreshCatalog]);

  const copyText = useCallback(async (text: string, ok: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setNotice(ok);
    } catch {
      setActionError("Could not copy to the clipboard.");
    }
  }, []);

  const exportEvidence = useCallback(async () => {
    const resp = await fetch("/api/audit/export", { method: "POST" });
    if (!resp.ok) {
      setActionError("Could not export audit evidence.");
      return;
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "audit-evidence.zip";
    a.click();
    URL.revokeObjectURL(url);
  }, []);

  const commands = useMemo(() => {
    const owned = new Set(sources.map((s) => s.name));
    return buildPaletteCommands({
      handlers: {
        run: () => void run(),
        cancel: () => void cancelRun(),
        newQueryTab,
        closeQueryTab: () => closeQueryTab(activeTabId),
        nextPage: () => {
          if (result?.truncated) void run(undefined, offset + PAGE_ROWS);
        },
        prevPage: () => {
          if (offset > 0) void run(undefined, Math.max(0, offset - PAGE_ROWS));
        },
        exportResult: () => void exportResult(),
        exportAs: (format) => void exportResult(format),
        snapshot,
        profile,
        explain,
        estimate: estimateCost,
        history: () => setShowHistory(true),
        goTab: (t) => (t === "profile" ? void profile() : setTab(t)),
        toggleAgentView: () => setAgentView((v) => !v),
        toggleTheme: () => setTheme((t) => (t === "dark" ? "light" : "dark")),
        help: () => setShowHelp(true),
        tour: () => setShowTutorial(true),
        explore: openExplore,
        ask: () => setDoor("ask"),
        govern: openGovern,
        connectLlm: () => {
          setDoor("ask");
          setConnectTick((n) => n + 1);
        },
        loadDemo: () => void loadDemo(),
        charterFiles: () => void charterFiles(),
        addSource: () => openGovern("sources"),
        uploadFile: () => fileRef.current?.click(),
        saveQuery: () => void saveQueryFile(),
        copyMarkdown: () => {
          const grid = agentView && agentResult ? agentResult : result;
          if (!grid) {
            setActionError("Run a query first.");
            return;
          }
          void copyText(
            resultToMarkdown(sqlRef.current, grid, {
              maskColumns: agentView && !agentResult ? maskedColumns : undefined,
            }),
            "Copied Markdown.",
          );
        },
        copyLink: () =>
          void copyText(
            `${window.location.origin}${window.location.pathname}${encodeQueryHash(sqlRef.current)}`,
            "Copied link to this query.",
          ),
        copySql: () => void copyText(sqlRef.current, "Copied SQL."),
        exportEvidence: () => {
          openGovern("audit");
          void exportEvidence();
        },
        runDataTests: () => {
          openGovern("evals");
          void api
            .runDataTests()
            .then((r) =>
              setNotice(r.passed ? "All data tests passed." : "Some data tests failed. See Evals."),
            )
            .catch((e) => setActionError((e as Error).message));
        },
        disconnectAgent: () =>
          void api.setAgentBackend("none").then(() => setNotice("Agent disconnected.")),
      },
      tables,
      metrics,
      queries: savedQueries,
      snapshots: tables.filter((t) => t.source === "local").map((t) => t.table),
      uploads: tables.filter((t) => t.source === "memory" && !owned.has(t.table)).map((t) => t.table),
      queryTabs,
      onOpenQuery: (name) => {
        void api.readQuery(name).then((b) => loadSql(b.sql)).catch((e) => setActionError((e as Error).message));
      },
      onRunMetric: (metricSql) => {
        loadSql(`${metricSql};\n`);
        void run(metricSql);
      },
      onOpenTable: pickRelation,
      onRecheck: (name) => {
        void api
          .recheckSnapshot(name)
          .then((r) =>
            setNotice(r.changed ? `Snapshot ${name} changed (−${r.gone} +${r.new}).` : `Snapshot ${name} unchanged.`),
          )
          .catch((e) => setActionError((e as Error).message));
      },
      onPromote: (name) => {
        void api
          .promoteUpload(name)
          .then(refreshCatalog)
          .catch((e) => setActionError((e as Error).message));
      },
      onSelectTab: selectQueryTab,
    });
  }, [
    run,
    cancelRun,
    exportResult,
    snapshot,
    profile,
    explain,
    estimateCost,
    pickRelation,
    tables,
    metrics,
    loadSql,
    result,
    offset,
    queryTabs,
    activeTabId,
    sources,
    savedQueries,
    agentView,
    agentResult,
    maskedColumns,
    copyText,
    saveQueryFile,
    exportEvidence,
    loadDemo,
    charterFiles,
    refreshCatalog,
    sql,
    error,
  ]);

  return (
    <div
      className={dragging ? "app dragging" : "app"}
      onDragOver={(e) => {
        // Only actual files get the drop overlay — dragging selected TEXT
        // (e.g. copying lines out of a chat answer) must not interrupt.
        if (!e.dataTransfer.types.includes("Files")) return;
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={(e) => {
        if (e.currentTarget === e.target) setDragging(false);
      }}
      onDrop={onDrop}
    >
      {dragging && <div className="drop-overlay">Drop csv / parquet / json to query it</div>}
      {degraded.map((w) => (
        <div key={w} className="degraded-banner" role="alert">
          ⚠ {w}
          <button aria-label="Dismiss warning" onClick={() => setDegraded((d) => d.filter((x) => x !== w))}>
            ×
          </button>
        </div>
      ))}
      {showTutorial && (
        <Tutorial
          actions={{
            loadAndRunExample,
            showChart: () => setTab("chart"),
            showProfile: profile,
            showView: (v) => (v === "explorer" ? openExplore() : openGovern(v as GovernPage)),
            toggleAgentView: () => setAgentView((v) => !v),
            runAgentExample,
          }}
          onClose={() => setShowTutorial(false)}
        />
      )}
      {showHelp && <HelpModal onClose={() => setShowHelp(false)} />}
      {showHistory && (
        <HistoryPanel onPick={(s) => loadSql(s)} onClose={() => setShowHistory(false)} />
      )}
      {actionError && <Toast message={actionError} onClose={() => setActionError(null)} />}
      {notice && (
        <Toast
          message={notice}
          onClose={() => setNotice(null)}
          timeoutMs={9000}
          variant="info"
        />
      )}
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
        <nav className="doors" aria-label="Mode">
          <button
            className={door === "explore" ? "door-btn on" : "door-btn"}
            onClick={openExplore}
          >
            Explore
          </button>
          <button
            className={door === "ask" ? "door-btn on" : "door-btn"}
            onClick={() => setDoor("ask")}
          >
            Ask
          </button>
          <button
            className={door === "govern" ? "door-btn on" : "door-btn"}
            onClick={() => openGovern(view === "explorer" ? "audit" : view)}
          >
            Govern
          </button>
        </nav>
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
        <button
          className="topbar-btn"
          onClick={() => setPaletteOpen(true)}
          title="Command palette (⌘K)"
        >
          ⌘K
        </button>
        <button className="topbar-btn" onClick={() => setShowHelp(true)} title="About & FAQ">
          Docs
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
            onRecheck={(name) => api.recheckSnapshot(name)}
            onPromote={(name) => {
              api.promoteUpload(name).then(refreshCatalog).catch((e) =>
                setActionError((e as Error).message),
              );
            }}
          />
        </aside>
        <div className="resizer-x" onMouseDown={sidebarW.onMouseDown} />
        <main className="main">
          {door === "ask" ? (
            <ChatPanel dark={dark} connectTick={connectTick} onOpenSql={(s) => { loadSql(s); openExplore(); setTab("sql"); }} />
          ) : door === "govern" ? (
            <>
              <div className="govern-nav">
                {(["audit", "studio", "sources", "evals", "guides"] as const).map((page) => (
                  <button
                    key={page}
                    className={view === page ? "door-btn on" : "door-btn"}
                    onClick={() => openGovern(page)}
                  >
                    {page[0].toUpperCase() + page.slice(1)}
                  </button>
                ))}
              </div>
              {view === "sources" ? (
                <SourcesView onChange={refreshCatalog} />
              ) : view === "studio" ? (
                <CharterStudio onSaved={refreshCatalog} />
              ) : view === "evals" ? (
                <EvalsView />
              ) : view === "guides" ? (
                <GuidesEditor />
              ) : (
                <AuditView />
              )}
            </>
          ) : shouldShowLaunchpad(catalogLoaded, sources.length, tables.length) ? (
            <EmptyState
              onAddSource={() => openGovern("sources")}
              onUpload={uploadFile}
              onLoadDemo={loadDemo}
              onCharterFiles={charterFiles}
            />
          ) : (
          <>
          <QueryTabs
            tabs={queryTabs}
            activeId={activeTabId}
            onSelect={selectQueryTab}
            onNew={newQueryTab}
            onClose={closeQueryTab}
          />
          <div className="toolbar">
              {running ? (
                <button
                  className="danger"
                  onClick={() => void cancelRun()}
                  title="Cancel the running query (Esc)"
                >
                  Cancel
                </button>
              ) : (
                <button
                  className="primary"
                  onClick={() => run()}
                  title="Run the query (⌘/Ctrl+Enter)"
                >
                  Run
                </button>
              )}
              <QueryFiles
                key={savedQueries.join(",")}
                currentSql={() => sqlRef.current}
                onLoad={loadSql}
              />
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
                onClick={() => void exportResult()}
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
          <section className="results-pane">
            <div className="tabs">
              <button
                className={tab === "results" ? "tab active" : "tab"}
                onClick={() => setTab("results")}
              >
                Data
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
                className={tab === "sql" ? "tab active" : "tab"}
                onClick={() => setTab("sql")}
              >
                SQL
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
              <div
                className={previewExpanded ? "preview-error expanded" : "preview-error"}
                title={previewExpanded ? "Click to collapse" : "Click to expand; text is selectable"}
                role="button"
                tabIndex={0}
                onClick={() => {
                  // Don't collapse under the user while they select text to copy.
                  if (window.getSelection()?.toString()) return;
                  setPreviewExpanded((v) => !v);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") setPreviewExpanded((v) => !v);
                }}
              >
                ⚠ live preview: {previewExpanded ? previewError : previewError.split("\n")[0]}
              </div>
            )}
            <div className="tab-body">
              {!error && tab === "sql" && (
                <div className="sql-tab">
                  <MonacoEditor
                    language="sql"
                    theme={dark ? "dc-dark" : "dc-light"}
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
                </div>
              )}
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
              {!error && tab === "results" && result && agentView && (
                agentRefusal ? (
                  <div className="agent-refusal">
                    <strong>Agent view — refused.</strong> This is exactly what a
                    connected agent gets for this query:
                    <pre>{agentRefusal}</pre>
                  </div>
                ) : agentResult ? (
                  <ResultsGrid result={agentResult} />
                ) : (
                  <div className="empty-state">Running the agent’s governed query…</div>
                )
              )}
              {!error && tab === "results" && result && !agentView && (
                <ResultsGrid
                  result={result}
                  offset={offset}
                  onPrev={() => void run(undefined, Math.max(0, offset - PAGE_ROWS))}
                  onNext={() => void run(undefined, offset + PAGE_ROWS)}
                />
              )}
              {!error && tab === "chart" && result && (
                <ChartPanel
                  result={agentView && agentResult ? agentResult : result}
                  dark={dark}
                  maskColumns={agentView && !agentResult ? maskedColumns : undefined}
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
              {!error && !result && tab !== "profile" && tab !== "sql" && (
                <div className="empty-state">Pick a table, or drop a file.</div>
              )}
            </div>
          </section>
          </>
          )}
        </main>
        {door === "explore" && !shouldShowLaunchpad(catalogLoaded, sources.length, tables.length) && (
          <>
            <div className="resizer-x" onMouseDown={chatW.onMouseDown} />
            <aside className="chat-dock" style={{ width: chatW.size }}>
              <ChatPanel dark={dark} connectTick={connectTick} onOpenSql={(s) => { loadSql(s); setTab("sql"); }} />
            </aside>
          </>
        )}
      </div>
      <input
        ref={fileRef}
        type="file"
        accept=".csv,.parquet,.json,.xlsx"
        style={{ display: "none" }}
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) void uploadFile(f);
          e.target.value = "";
        }}
      />
    </div>
  );
}
