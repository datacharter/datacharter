import { describe, expect, it } from "vitest";

import { exampleFor, shouldShowTour } from "./onboarding";

const tbl = (source: string, table: string) => ({ source, schema: "main", table, columns: [] });

describe("exampleFor", () => {
  it("empty workspace -> starter", () => expect(exampleFor([])).toContain("SELECT 42"));
  it("demo store present -> aggregation", () =>
    expect(exampleFor([tbl("store", "orders")])).toContain("FROM store.orders\nGROUP BY"));
  it("own table -> scan", () =>
    expect(exampleFor([tbl("crm", "accounts")])).toContain("FROM crm.accounts"));
});

describe("shouldShowTour", () => {
  it("empty -> false", () => expect(shouldShowTour(false, 0, true)).toBe(false));
  it("populated + unseen + loaded -> true", () => expect(shouldShowTour(false, 2, true)).toBe(true));
  it("not loaded yet -> false", () => expect(shouldShowTour(false, 2, false)).toBe(false));
  it("already seen -> false", () => expect(shouldShowTour(true, 2, true)).toBe(false));
});
