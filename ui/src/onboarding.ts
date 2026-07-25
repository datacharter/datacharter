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

// The guided tour auto-shows only on a populated workspace; empty workspaces get the
// launchpad instead.
export function shouldShowTour(seen: boolean, sourceCount: number, loaded: boolean): boolean {
  return loaded && !seen && sourceCount > 0;
}
