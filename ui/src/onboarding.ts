import type { TableInfo } from "./api";

export const STARTER = "-- Cmd/Ctrl+Enter to run\nSELECT 42 AS answer;\n";
const EXAMPLE_SQL =
  "SELECT customer_id, count(*) AS orders, round(sum(total), 2) AS revenue\n" +
  "FROM store.orders\nGROUP BY customer_id\nORDER BY revenue DESC;\n";

// The example must reference a table that exists: the demo aggregation when the demo
// `store` source is present, else a scan of the first real table, else the starter.
export function exampleFor(tables: TableInfo[]): string {
  if (tables.some((t) => t.source === "store" && t.table === "orders")) return EXAMPLE_SQL;
  const first = tables[0];
  if (first) return `SELECT *\nFROM ${first.source}.${first.table}\nLIMIT 100;\n`;
  return STARTER;
}

// The Agent-view tour step needs a query whose result actually contains a masked
// column — otherwise the toggle changes nothing. Prefer the canaries snapshot: it
// carries masked PII by design and no aggregates-only policy blocks a raw SELECT
// (unlike the policied demo customers table).
export function agentExampleFor(tables: TableInfo[]): string | null {
  const masked = tables.filter((t) =>
    Object.values(t.access ?? {}).some((a) => a.masked),
  );
  if (masked.length === 0) return null;
  const pick =
    masked.find((t) => t.table === "canaries") ??
    masked.find((t) => t.table !== "customers") ??
    masked[0];
  return `SELECT ${pick.columns.join(", ")}\nFROM ${pick.source}.${pick.table}\nLIMIT 5;\n`;
}

// The guided tour auto-shows only on a populated workspace; empty workspaces get the
// launchpad instead.
export function shouldShowTour(seen: boolean, sourceCount: number, loaded: boolean): boolean {
  return loaded && !seen && sourceCount > 0;
}

// The launchpad shows only when there is nothing to explore. An uploaded CSV registers a
// queryable table without a charter source, so gate on tables too — else the launchpad
// would trap the user after an upload.
export function shouldShowLaunchpad(loaded: boolean, sourceCount: number, tableCount: number): boolean {
  return loaded && sourceCount === 0 && tableCount === 0;
}
