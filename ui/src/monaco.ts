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

// Explicit suggest-widget colors. Monaco's default vs/vs-dark themes inject
// these via a path that WebKit (the desktop app's WKWebView) renders wrong —
// white label text on a light widget, i.e. invisible. Pinning concrete values
// in a named theme sidesteps that. Use these themes instead of "vs"/"vs-dark".
monaco.editor.defineTheme("dc-light", {
  base: "vs",
  inherit: true,
  rules: [],
  colors: {
    "editorSuggestWidget.background": "#ffffff",
    "editorSuggestWidget.foreground": "#1b2531",
    "editorSuggestWidget.selectedBackground": "#e8f0fe",
    "editorSuggestWidget.selectedForeground": "#1b2531",
    "editorSuggestWidget.highlightForeground": "#0a66c2",
    "editorSuggestWidget.focusHighlightForeground": "#0a66c2",
    "editorSuggestWidget.border": "#d5dbe2",
  },
});
monaco.editor.defineTheme("dc-dark", {
  base: "vs-dark",
  inherit: true,
  rules: [],
  colors: {
    "editorSuggestWidget.background": "#1e2530",
    "editorSuggestWidget.foreground": "#dce3ea",
    "editorSuggestWidget.selectedBackground": "#2a3646",
    "editorSuggestWidget.selectedForeground": "#ffffff",
    "editorSuggestWidget.highlightForeground": "#6ca8ff",
    "editorSuggestWidget.focusHighlightForeground": "#6ca8ff",
    "editorSuggestWidget.border": "#33404f",
  },
});

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
    // Pop suggestions where a column/table is expected: after `.` (scoped),
    // and proactively after a space, comma, or `(` — not only while a word is
    // being typed. Without these, columns never appear after `SELECT `/`, `.
    triggerCharacters: [".", ",", " ", "("],
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
        const inSource = tables.filter(
          (t) => t.source.toLowerCase() === qualifier && String(t.table).trim(),
        );
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
        // Unknown qualifier (typo, a CTE, or catalog not loaded yet): fall
        // through to the full list rather than showing an empty widget.
      }

      // Rank the group the user most likely wants to the TOP: tables right
      // after FROM/JOIN, columns everywhere else — keywords always last, so a
      // data editor surfaces your schema, not `AND`/`AS`, first. (Monaco sorts
      // by sortText; the numeric prefix decides the group order.)
      const afterFrom = /\b(?:from|join)\s+[\w.]*$/.test(lineToCursor);
      const colRank = afterFrom ? "2" : "0";
      const tblRank = afterFrom ? "0" : "1";

      const suggestions: monaco.languages.CompletionItem[] = [];
      for (const t of tables) {
        const relation = String(relationOf(t)).trim();
        if (!relation) continue; // never emit a blank-label row
        suggestions.push({
          label: relation,
          kind: m.languages.CompletionItemKind.Class,
          insertText: relation,
          detail: `${t.columns.length} columns`,
          sortText: `${tblRank}_${relation}`,
          range,
        });
      }
      // Every column of every table (qualified in `detail`) — no cross-table
      // dedup, so a column shared by two tables still shows both.
      for (const t of tables) {
        for (const col of t.columns ?? []) {
          const name = String(col).trim();
          if (!name) continue; // a source can yield an unnamed column — skip it
          suggestions.push({
            label: name,
            kind: m.languages.CompletionItemKind.Field,
            insertText: name,
            detail: relationOf(t),
            sortText: `${colRank}_${name}`,
            range,
          });
        }
      }
      for (const kw of KEYWORDS) {
        suggestions.push({
          label: kw,
          kind: m.languages.CompletionItemKind.Keyword,
          insertText: kw,
          sortText: `9_${kw}`,
          range,
        });
      }
      return { suggestions };
    },
  });
}

