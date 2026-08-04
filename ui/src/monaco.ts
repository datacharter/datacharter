// Bundle Monaco locally (DESIGN D1: fully offline, no CDN).
import { loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor";
import editorWorker from "monaco-editor/editor/editor.worker.js?worker";
import type { TableInfo } from "./api";
import { columnsForQualifier } from "./lib/completion";

self.MonacoEnvironment = {
  getWorker: () => new editorWorker(),
};

loader.config({ monaco });

const KEYWORDS = [
  "SELECT", "FROM", "WHERE", "GROUP BY", "ORDER BY", "HAVING", "LIMIT", "OFFSET",
  "JOIN", "LEFT JOIN", "INNER JOIN", "FULL JOIN", "ON", "USING", "AS", "WITH",
  "UNION", "UNION ALL", "DISTINCT", "CASE", "WHEN", "THEN", "ELSE", "END",
  "AND", "OR", "NOT", "IN", "BETWEEN", "LIKE", "ILIKE", "IS NULL", "IS NOT NULL",
  "COUNT", "SUM", "AVG", "MIN", "MAX", "COALESCE", "CAST", "EXTRACT",
  "DATE_TRUNC", "SUMMARIZE", "DESCRIBE", "EXPLAIN", "QUALIFY", "PIVOT", "UNPIVOT",
];

let registered = false;

/** Schema-aware completions: live tables/columns + core keyword set. */
export function registerCompletions(
  m: typeof monaco,
  getTables: () => TableInfo[],
): void {
  if (registered) return;
  registered = true;
  m.languages.registerCompletionItemProvider("sql", {
    // `.` so `customers.` or an alias `c.` triggers scoped column completion.
    triggerCharacters: ["."],
    provideCompletionItems(model, position) {
      const word = model.getWordUntilPosition(position);
      const range = new m.Range(
        position.lineNumber,
        word.startColumn,
        position.lineNumber,
        word.endColumn,
      );
      const tables = getTables();
      const relationOf = (t: TableInfo) =>
        t.source === "memory" ? t.table : `${t.source}.${t.table}`;

      // What precedes the cursor: a `qualifier.` means scope to that relation.
      const lineToCursor = model
        .getValueInRange(
          new m.Range(position.lineNumber, 1, position.lineNumber, position.column),
        )
        .toLowerCase();
      const qualMatch = lineToCursor.match(/([\w.]+)\.\w*$/);

      if (qualMatch) {
        const qualifier = qualMatch[1]; // e.g. "customers", "store.customers", alias "c"
        const cols = columnsForQualifier(qualifier, tables, model.getValue());
        if (cols) {
          return {
            suggestions: cols.map((col) => ({
              label: col.name,
              kind: m.languages.CompletionItemKind.Field,
              insertText: col.name,
              detail: col.relation,
              range,
            })),
          };
        }
        // Qualifier is a source/schema (`store.`): offer its tables.
        const inSource = tables.filter((t) => t.source.toLowerCase() === qualifier);
        if (inSource.length) {
          return {
            suggestions: inSource.map((t) => ({
              label: t.table,
              kind: m.languages.CompletionItemKind.Class,
              insertText: t.table,
              detail: `${t.columns.length} columns`,
              range,
            })),
          };
        }
        return { suggestions: [] };
      }

      const suggestions: monaco.languages.CompletionItem[] = [];
      for (const kw of KEYWORDS) {
        suggestions.push({
          label: kw,
          kind: m.languages.CompletionItemKind.Keyword,
          insertText: kw,
          range,
        });
      }
      for (const t of tables) {
        const relation = relationOf(t);
        suggestions.push({
          label: relation,
          kind: m.languages.CompletionItemKind.Class,
          insertText: relation,
          detail: `${t.columns.length} columns`,
          range,
        });
      }
      // Every column of every table (qualified in `detail`) — no cross-table
      // dedup, so a column shared by two tables still shows both.
      for (const t of tables) {
        for (const col of t.columns) {
          suggestions.push({
            label: col,
            kind: m.languages.CompletionItemKind.Field,
            insertText: col,
            detail: relationOf(t),
            range,
          });
        }
      }
      return { suggestions };
    },
  });
}

