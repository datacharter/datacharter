import { describe, expect, it } from "vitest";

import { agentExampleFor, exampleFor, shouldShowLaunchpad, shouldShowTour } from "./onboarding";

const tbl = (source: string, table: string) => ({ source, schema: "main", table, columns: [] });
const maskedTbl = (source: string, table: string, columns: string[], maskedCol: string) => ({
  source,
  schema: "main",
  table,
  columns,
  access: Object.fromEntries(
    columns.map((c) => [c, { masked: c === maskedCol, pii: c === maskedCol }]),
  ),
});

describe("exampleFor", () => {
  it("empty workspace -> starter", () => expect(exampleFor([])).toContain("SELECT 42"));
  it("demo store present -> aggregation", () =>
    expect(exampleFor([tbl("store", "orders")])).toContain("FROM store.orders\nGROUP BY"));
  it("own table -> scan", () =>
    expect(exampleFor([tbl("crm", "accounts")])).toContain("FROM crm.accounts"));
});

describe("agentExampleFor", () => {
  it("no masked columns anywhere -> null", () =>
    expect(agentExampleFor([tbl("crm", "accounts")])).toBeNull());
  it("prefers the canaries snapshot over policied customers", () => {
    const sql = agentExampleFor([
      maskedTbl("store", "customers", ["id", "email", "tier"], "email"),
      maskedTbl("local", "canaries", ["email", "phone", "ssn"], "email"),
    ]);
    expect(sql).toContain("FROM local.canaries");
  });
  it("falls back to any masked table", () => {
    const sql = agentExampleFor([
      tbl("crm", "accounts"),
      maskedTbl("hr", "people", ["name", "ssn"], "ssn"),
    ]);
    expect(sql).toContain("FROM hr.people");
    expect(sql).toContain("name, ssn");
  });
});

describe("shouldShowTour", () => {
  it("empty -> false", () => expect(shouldShowTour(false, 0, true)).toBe(false));
  it("populated + unseen + loaded -> true", () => expect(shouldShowTour(false, 2, true)).toBe(true));
  it("not loaded yet -> false", () => expect(shouldShowTour(false, 2, false)).toBe(false));
  it("already seen -> false", () => expect(shouldShowTour(true, 2, true)).toBe(false));
});

describe("shouldShowLaunchpad", () => {
  it("nothing to explore -> true", () => expect(shouldShowLaunchpad(true, 0, 0)).toBe(true));
  it("an uploaded table (no source) -> false", () =>
    expect(shouldShowLaunchpad(true, 0, 1)).toBe(false));
  it("a source present -> false", () => expect(shouldShowLaunchpad(true, 1, 0)).toBe(false));
  it("not loaded yet -> false", () => expect(shouldShowLaunchpad(false, 0, 0)).toBe(false));
});
