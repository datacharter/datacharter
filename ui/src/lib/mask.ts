import type { QueryResult } from "../api";

/** A copy of `result` with the named columns (and their row cells) removed. */
export function withoutColumns(result: QueryResult, names: Set<string>): QueryResult {
  const lower = new Set([...names].map((n) => n.toLowerCase()));
  const keep = result.columns
    .map((c, i) => [c, i] as const)
    .filter(([c]) => !lower.has(c.toLowerCase()));
  return {
    ...result,
    columns: keep.map(([c]) => c),
    rows: result.rows.map((row) => keep.map(([, i]) => row[i])),
  };
}

export interface ExportPlan {
  body: { sql: string; format: string; mask_columns?: string[]; agent_view?: boolean };
  filename: string;
}

/** Build the /api/export request body + download filename for the current view. */
export function exportRequest(
  sql: string,
  format: string,
  agentView: boolean,
  masked: Set<string>,
  resultColumns: string[],
): ExportPlan {
  const maskCols = agentView ? resultColumns.filter((c) => masked.has(c.toLowerCase())) : [];
  // agent_view lets the SERVER add the charter's PII floor authoritatively, so
  // an agent-view export can't leak raw PII even if maskCols is incomplete.
  return {
    body: agentView ? { sql, format, mask_columns: maskCols, agent_view: true } : { sql, format },
    filename: `datacharter-export${agentView ? "-agent-view" : ""}.${format}`,
  };
}
