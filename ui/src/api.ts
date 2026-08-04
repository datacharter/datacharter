export interface SourceInfo {
  name: string;
  type: string;
  path: string | null;
  tables: string[];
  pii: Record<string, string[]>;
  connection?: Record<string, string | number>;
  has_credential?: boolean;
}

export interface SourceFormData {
  name: string;
  type: string;
  connection: Record<string, string | number>;
  password?: string;
  path?: string;
  tables: string[];
  pii: Record<string, string[]>;
  max_rows?: number;
}

export interface ColumnAccess {
  masked: boolean;
  pii: boolean;
}

export interface TableInfo {
  source: string;
  schema: string;
  table: string;
  columns: string[];
  access?: Record<string, ColumnAccess>;
}

export interface Provenance {
  relations: string[];
  columns: string[];
}

export interface QueryResult {
  columns: string[];
  rows: unknown[][];
  row_count: number;
  truncated: boolean;
  warnings?: string[];
  provenance?: Provenance | null;
  top_values?: Record<string, [unknown, number][]> | null;
}

export interface HistoryEntry {
  ts: string;
  sql: string;
  row_count: number;
  relations: string[];
  columns: string[];
}

export interface ApiError {
  type: string;
  message: string;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(path, init);
  const body = await resp.json();
  if (!resp.ok) {
    const err = (body?.error ?? { type: "http_error", message: resp.statusText }) as ApiError;
    throw Object.assign(new Error(err.message), { kind: err.type });
  }
  return body as T;
}

export const api = {
  sources: () =>
    request<{ sources: SourceInfo[]; warnings: string[] }>("/api/sources"),
  tables: () => request<{ tables: TableInfo[] }>("/api/tables"),
  query: (sql: string, rowLimit = 10000, record = false) =>
    request<QueryResult>("/api/query", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ sql, row_limit: rowLimit, record }),
    }),
  history: (limit = 50) =>
    request<{ entries: HistoryEntry[] }>(`/api/history?limit=${limit}`),
  explain: (sql: string) =>
    request<{ plan: string; estimated_rows: number | null }>("/api/explain", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ sql }),
    }),
  profile: (sql: string) =>
    request<QueryResult>("/api/profile", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ sql }),
    }),
  createSource: (f: SourceFormData) =>
    request<{ name: string }>("/api/sources", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(f),
    }),
  updateSource: (name: string, f: SourceFormData) =>
    request<{ name: string }>(`/api/sources/${name}`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(f),
    }),
  deleteSource: (name: string) =>
    request<{ removed: string }>(`/api/sources/${name}`, { method: "DELETE" }),
  loadDemo: () =>
    request<{ sources: SourceInfo[] }>("/api/demo", { method: "POST" }),
  setAgentAccess: (a: { source: string; table?: string; column?: string; value: boolean }) =>
    request<{ ok: boolean }>("/api/agent-access", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(a),
    }),
  deleteSnapshot: (name: string) =>
    request<{ removed: string }>(`/api/snapshot/${name}`, { method: "DELETE" }),
  deleteUpload: (name: string) =>
    request<{ removed: string }>(`/api/uploads/${name}`, { method: "DELETE" }),
  testSource: (f: SourceFormData) =>
    request<{ ok: boolean }>("/api/sources/test", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(f),
    }),
  agentStatus: () =>
    request<AgentStatus>("/api/agent/available"),
  configureLLM: (c: { base_url?: string; api_key?: string; model?: string }) =>
    request<AgentStatus>("/api/agent/config", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(c),
    }),
  connectClaudeCode: () =>
    request<{ backend: string }>("/api/agent/claude-code/connect", { method: "POST" }),
  setAgentBackend: (backend: string) =>
    request<{ backend: string }>("/api/agent/backend", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ backend }),
    }),
  auditLog: () => request<AuditPayload>("/api/audit"),
  auditVerify: () => request<AuditVerify>("/api/audit/verify"),
  canaryStatus: () => request<{ armed: boolean; mode: string | null }>("/api/canary"),
  listEvals: () => request<{ suites: EvalSuite[] }>("/api/evals"),
  evalHistory: () => request<{ runs: EvalRun[] }>("/api/evals/history"),
  listGuides: () => request<GuidesPayload>("/api/guides"),
  guideSuggestions: () =>
    request<{ suggestions: { kind: string; relation: string; text: string; count: number; total: number }[] }>(
      "/api/guides/suggestions",
    ),
  saveGuide: (body: {
    name?: string;
    content?: string;
    source?: string;
    table?: string;
    context?: string;
  }) =>
    request<{ saved: boolean }>("/api/guides", {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    }),
  deleteGuide: (name: string) =>
    request<{ removed: string }>(`/api/guides/${name}`, { method: "DELETE" }),
  listEvalFiles: () =>
    request<{ files: { name: string; content: string }[] }>("/api/evals/files"),
  saveEvalFile: (name: string, content: string) =>
    request<{ saved: string }>(`/api/evals/files/${name}`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ content }),
    }),
  deleteEvalFile: (name: string) =>
    request<{ removed: string }>(`/api/evals/files/${name}`, { method: "DELETE" }),
  recheckSnapshot: (name: string) =>
    request<{ changed: boolean; gone: number; new: number }>(
      `/api/snapshot/${name}/recheck`,
      { method: "POST" },
    ),
  listMetrics: () =>
    request<{ metrics: { name: string; sql: string; dimensions: string[]; has_time: boolean }[] }>(
      "/api/metrics",
    ),
  localLLMs: () =>
    request<{ runtimes: { provider: string; base_url: string; models: string[] }[] }>(
      "/api/llm/local",
    ),
  runDataTests: () =>
    request<{
      results: { name: string; passed: boolean; failing_rows?: number; error?: string }[];
      passed: boolean;
    }>("/api/tests/run", { method: "POST" }),
};

export interface AuditEntry {
  seq: number;
  ts: string;
  type: "session" | "access";
  session: string;
  surface?: string;
  user?: string;
  client?: { name?: string; version?: string } | null;
  model?: string | null;
  question?: string | null;
  tool?: string;
  sql?: string | null;
  relation?: string | null;
  row_count?: number | null;
  masked_columns?: string[];
  relations?: string[];
  error?: string | null;
}

export interface AuditPayload {
  sessions: AuditEntry[];
  entries: AuditEntry[];
}

export interface AuditVerify {
  ok: boolean;
  entries: number;
  detail: string;
}

export interface EvalSuite {
  name: string;
  cases: { question: string }[];
}

export interface EvalCaseOutcome {
  passed: boolean;
  answer: string;
  sqls: string[];
}

export interface EvalRun {
  started_at?: string;
  suite: string;
  overall: { with_guides: number; without_guides?: number; lift?: number };
  cases: { question: string; with_guides: EvalCaseOutcome }[];
}

export interface GuidesPayload {
  guides: { name: string; content: string }[];
  contexts: { source: string; table: string; context: string }[];
}

export interface AgentStatus {
  available: boolean;
  model: string | null;
  base_url: string | null;
  has_key: boolean;
  backend?: string;
  claude_code_available?: boolean;
}
