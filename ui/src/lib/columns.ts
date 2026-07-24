import type { QueryResult } from "../api";

export type ColumnClass = "numeric" | "date" | "categorical";

const DATE_RE = /^\d{4}-\d{2}-\d{2}([T ].*)?$/;

/** Classify columns from a sample of result rows (drives chart auto-detect). */
export function classifyColumns(result: QueryResult): Map<string, ColumnClass> {
  const classes = new Map<string, ColumnClass>();
  const sample = result.rows.slice(0, 200);
  result.columns.forEach((name, i) => {
    const values = sample.map((r) => r[i]).filter((v) => v !== null && v !== undefined);
    if (values.length === 0) {
      classes.set(name, "categorical");
      return;
    }
    if (values.every((v) => typeof v === "number" || typeof v === "bigint")) {
      classes.set(name, "numeric");
    } else if (values.every((v) => typeof v === "string" && DATE_RE.test(v))) {
      classes.set(name, "date");
    } else {
      classes.set(name, "categorical");
    }
  });
  return classes;
}
