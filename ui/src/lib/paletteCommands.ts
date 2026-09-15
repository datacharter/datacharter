import type { Command } from "./commandPalette";

export interface PaletteHandlers {
  run: () => void;
  cancel: () => void;
  newQueryTab: () => void;
  closeQueryTab: () => void;
  nextPage: () => void;
  prevPage: () => void;
  exportResult: () => void;
  exportAs: (format: string) => void;
  snapshot: () => void;
  profile: () => void;
  explain: () => void;
  estimate: () => void;
  history: () => void;
  goTab: (tab: "results" | "chart" | "profile" | "plan" | "sql") => void;
  toggleAgentView: () => void;
  toggleTheme: () => void;
  help: () => void;
  tour: () => void;
  explore: () => void;
  ask: () => void;
  govern: (page: "audit" | "studio" | "sources" | "evals" | "guides") => void;
  connectLlm: () => void;
  loadDemo: () => void;
  charterFiles: () => void;
  addSource: () => void;
  uploadFile: () => void;
  saveQuery: () => void;
  copyMarkdown: () => void;
  copyLink: () => void;
  copySql: () => void;
  exportEvidence: () => void;
  runDataTests: () => void;
  disconnectAgent: () => void;
}

export const CORE_ACTION_IDS = [
  "run",
  "cancel",
  "new-query",
  "close-query",
  "page-next",
  "page-prev",
  "export",
  "export-csv",
  "export-parquet",
  "export-json",
  "export-xlsx",
  "snapshot",
  "profile",
  "explain",
  "estimate",
  "history",
  "tab-results",
  "tab-chart",
  "tab-profile",
  "tab-plan",
  "tab-sql",
  "agent-view",
  "theme",
  "help",
  "tour",
  "door-explore",
  "door-ask",
  "door-govern",
  "door-studio",
  "door-sources",
  "door-evals",
  "door-guides",
  "door-audit",
  "connect-llm",
  "disconnect-agent",
  "load-demo",
  "charter-files",
  "add-source",
  "upload-file",
  "save-query",
  "copy-markdown",
  "copy-link",
  "copy-sql",
  "export-evidence",
  "run-tests",
] as const;

export function buildPaletteCommands(input: {
  handlers: PaletteHandlers;
  tables: { source: string; table: string }[];
  metrics: { name: string; sql: string }[];
  queries: string[];
  snapshots?: string[];
  uploads?: string[];
  queryTabs?: { id: string; title: string }[];
  onOpenQuery?: (name: string) => void;
  onRunMetric?: (sql: string) => void;
  onOpenTable?: (relation: string) => void;
  onRecheck?: (name: string) => void;
  onPromote?: (name: string) => void;
  onSelectTab?: (id: string) => void;
}): Command[] {
  const h = input.handlers;
  const a = (id: string, label: string, run: () => void, hint?: string): Command => ({
    id,
    label,
    hint,
    run,
  });
  const actions: Command[] = [
    a("run", "Run query", h.run, "Query"),
    a("cancel", "Cancel query", h.cancel, "Query"),
    a("new-query", "New query tab", h.newQueryTab, "Query"),
    a("close-query", "Close query tab", h.closeQueryTab, "Query"),
    a("page-next", "Next page", h.nextPage, "Query"),
    a("page-prev", "Previous page", h.prevPage, "Query"),
    a("save-query", "Save query to queries/", h.saveQuery, "Query"),
    a("copy-sql", "Copy SQL", h.copySql, "Query"),
    a("copy-link", "Copy link to query", h.copyLink, "Query"),
    a("copy-markdown", "Copy result as Markdown", h.copyMarkdown, "Query"),
    a("export", "Export result", h.exportResult, "Query"),
    a("export-csv", "Export as CSV", () => h.exportAs("csv"), "Query"),
    a("export-parquet", "Export as Parquet", () => h.exportAs("parquet"), "Query"),
    a("export-json", "Export as JSON", () => h.exportAs("json"), "Query"),
    a("export-xlsx", "Export as XLSX", () => h.exportAs("xlsx"), "Query"),
    a("snapshot", "Snapshot result", h.snapshot, "Query"),
    a("profile", "Profile", h.profile, "Query"),
    a("explain", "Explain plan", h.explain, "Query"),
    a("estimate", "Estimate cost", h.estimate, "Query"),
    a("history", "Query history", h.history, "View"),
    a("tab-results", "Go to Data", () => h.goTab("results"), "View"),
    a("tab-chart", "Go to Chart", () => h.goTab("chart"), "View"),
    a("tab-profile", "Go to Profile", () => h.goTab("profile"), "View"),
    a("tab-plan", "Go to Plan", () => h.goTab("plan"), "View"),
    a("tab-sql", "Go to SQL", () => h.goTab("sql"), "View"),
    a("agent-view", "Toggle Agent view", h.toggleAgentView, "View"),
    a("theme", "Toggle theme", h.toggleTheme, "View"),
    a("help", "Help, About and FAQ", h.help, "View"),
    a("tour", "Take the tour", h.tour, "View"),
    a("door-explore", "Explore", h.explore, "View"),
    a("door-ask", "Ask", h.ask, "View"),
    a("connect-llm", "Connect an LLM", h.connectLlm, "Connect"),
    a("disconnect-agent", "Disconnect agent", h.disconnectAgent, "Connect"),
    a("door-govern", "Govern", () => h.govern("audit"), "Govern"),
    a("door-audit", "Audit", () => h.govern("audit"), "Govern"),
    a("door-studio", "Charter Studio", () => h.govern("studio"), "Govern"),
    a("door-sources", "Sources", () => h.govern("sources"), "Govern"),
    a("door-evals", "Evals", () => h.govern("evals"), "Govern"),
    a("door-guides", "Guides", () => h.govern("guides"), "Govern"),
    a("export-evidence", "Export audit evidence", h.exportEvidence, "Govern"),
    a("run-tests", "Run data tests", h.runDataTests, "Govern"),
    a("add-source", "Add a source", h.addSource, "Data"),
    a("upload-file", "Upload a file", h.uploadFile, "Data"),
    a("charter-files", "Charter files in this folder", h.charterFiles, "Data"),
    a("load-demo", "Load the demo dataset", h.loadDemo, "Data"),
  ];
  const tableCmds = input.tables.map((t) => {
    const rel = t.source === "memory" ? t.table : `${t.source}.${t.table}`;
    return a(`open:${rel}`, `Open ${rel}`, () => input.onOpenTable?.(rel), "Catalog");
  });
  const metricCmds = input.metrics.map((m) =>
    a(`metric:${m.name}`, `Run metric: ${m.name}`, () => input.onRunMetric?.(m.sql), "Catalog"),
  );
  const queryCmds = input.queries.map((name) =>
    a(`query:${name}`, `Open query ${name}`, () => input.onOpenQuery?.(name), "Catalog"),
  );
  const snapCmds = (input.snapshots ?? []).map((name) =>
    a(`recheck:${name}`, `Recheck snapshot ${name}`, () => input.onRecheck?.(name), "Catalog"),
  );
  const uploadCmds = (input.uploads ?? []).map((name) =>
    a(`promote:${name}`, `Promote upload ${name}`, () => input.onPromote?.(name), "Catalog"),
  );
  const tabCmds = (input.queryTabs ?? []).map((t) =>
    a(`tab:${t.id}`, `Go to ${t.title}`, () => input.onSelectTab?.(t.id), "Query"),
  );
  return [
    ...actions,
    ...metricCmds,
    ...tableCmds,
    ...queryCmds,
    ...snapCmds,
    ...uploadCmds,
    ...tabCmds,
  ];
}
