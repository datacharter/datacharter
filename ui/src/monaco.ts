// Bundle Monaco locally (DESIGN D1: fully offline, no CDN).
import { loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor";
import editorWorker from "monaco-editor/editor/editor.worker.js?worker";
import type { TableInfo } from "./api";

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
    provideCompletionItems(model, position) {
      const word = model.getWordUntilPosition(position);
      const range = new m.Range(
        position.lineNumber,
        word.startColumn,
        position.lineNumber,
        word.endColumn,
      );
      const tables = getTables();
      const suggestions: monaco.languages.CompletionItem[] = [];

      for (const kw of KEYWORDS) {
        suggestions.push({
          label: kw,
          kind: m.languages.CompletionItemKind.Keyword,
          insertText: kw,
          range,
        });
      }
      const seenColumns = new Set<string>();
      for (const t of tables) {
        const relation = t.source === "memory" ? t.table : `${t.source}.${t.table}`;
        suggestions.push({
          label: relation,
          kind: m.languages.CompletionItemKind.Class,
          insertText: relation,
          detail: `${t.columns.length} columns`,
          range,
        });
        for (const col of t.columns) {
          if (seenColumns.has(col)) continue;
          seenColumns.add(col);
          suggestions.push({
            label: col,
            kind: m.languages.CompletionItemKind.Field,
            insertText: col,
            detail: t.table,
            range,
          });
        }
      }
      return { suggestions };
    },
  });
}
