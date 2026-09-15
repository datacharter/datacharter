import type { QueryResult } from "../api";

const MASK = "•••";

function cell(value: unknown, masked: boolean): string {
  if (masked) return MASK;
  if (value === null || value === undefined) return "∅";
  return String(value).replace(/\|/g, "\\|").replace(/\n/g, " ");
}

/** Markdown a coworker can paste: fenced SQL, a table, a one-line footer. */
export function resultToMarkdown(
  sql: string,
  result: QueryResult,
  opts?: { maskColumns?: Set<string>; maxRows?: number },
): string {
  const maxRows = opts?.maxRows ?? 50;
  const mask = opts?.maskColumns;
  const maskIdx = new Set(
    result.columns
      .map((name, i) => (mask?.has(name.toLowerCase()) ? i : -1))
      .filter((i) => i >= 0),
  );
  const rows = result.rows.slice(0, maxRows);
  const header = `| ${result.columns.join(" | ")} |`;
  const sep = `| ${result.columns.map(() => "---").join(" | ")} |`;
  const body = rows
    .map(
      (row) =>
        `| ${result.columns.map((_, i) => cell(row[i], maskIdx.has(i))).join(" | ")} |`,
    )
    .join("\n");
  const omitted = result.rows.length - rows.length;
  const extra = omitted > 0 ? `\n\n… ${omitted} more rows` : "";
  const rels = result.provenance?.relations.join(", ") || "result";
  const footer = `_Reads ${rels} · ${result.row_count.toLocaleString()} rows · DataCharter_`;
  return `\`\`\`sql\n${sql.trim()}\n\`\`\`\n\n${header}\n${sep}\n${body}${extra}\n\n${footer}\n`;
}
