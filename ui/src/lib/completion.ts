// Pure SQL-completion resolution — no monaco import, so it's unit-testable.
import type { TableInfo } from "../api";

const KEYWORD_SET = new Set([
  "on", "using", "where", "group", "order", "having", "limit", "as", "select", "from", "join",
]);

const relationOf = (t: TableInfo) =>
  (t.source === "memory" ? t.table : `${t.source}.${t.table}`).toLowerCase();

/** Columns for a `qualifier.` prefix — matching a table name, a full
 *  `source.table`, or a FROM/JOIN alias bound in the query text. Returns null
 *  when the qualifier resolves to no table (caller may then try source→tables). */
export function columnsForQualifier(
  qualifier: string,
  tables: TableInfo[],
  fullSql: string,
): { name: string; relation: string }[] | null {
  const q = qualifier.toLowerCase();
  const aliases = new Map<string, string>();
  const re = /\b(?:from|join)\s+([\w.]+)(?:\s+as)?\s+([a-z_]\w*)/gi;
  let match: RegExpExecArray | null;
  while ((match = re.exec(fullSql)) !== null) {
    const alias = match[2].toLowerCase();
    if (!KEYWORD_SET.has(alias)) aliases.set(alias, match[1].toLowerCase());
  }
  const target = aliases.get(q) ?? q;
  const t = tables.find((tb) => relationOf(tb) === target || tb.table.toLowerCase() === target);
  if (!t) return null;
  return (t.columns ?? [])
    .map((c) => String(c).trim())
    .filter(Boolean) // a source can yield an unnamed column — never a blank row
    .map((name) => ({ name, relation: relationOf(t) }));
}
