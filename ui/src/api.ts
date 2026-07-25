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
  query: (sql: string, rowLimit = 10000) =>
    request<QueryResult>("/api/query", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ sql, row_limit: rowLimit }),
    }),
  profile: (relation: string) =>
    request<QueryResult>("/api/profile", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ relation }),
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
};

export interface AgentStatus {
  available: boolean;
  model: string | null;
  base_url: string | null;
  has_key: boolean;
  backend?: string;
  claude_code_available?: boolean;
}
