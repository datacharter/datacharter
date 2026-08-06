import { describe, expect, it } from "vitest";
import type { TableInfo } from "../api";
import { columnsForQualifier } from "./completion";

const TABLES = [
  { source: "store", schema: "main", table: "customers", columns: ["id", "email", "tier"], access: {} },
  { source: "store", schema: "main", table: "orders", columns: ["id", "total"], access: {} },
] as unknown as TableInfo[];

const names = (r: { name: string }[] | null) => (r ? r.map((c) => c.name) : null);

describe("columnsForQualifier", () => {
  it("resolves a bare table name to its columns", () => {
    expect(names(columnsForQualifier("customers", TABLES, "SELECT customers."))).toEqual([
      "id", "email", "tier",
    ]);
  });

  it("resolves a fully-qualified source.table", () => {
    expect(names(columnsForQualifier("store.orders", TABLES, "SELECT store.orders."))).toEqual([
      "id", "total",
    ]);
  });

  it("resolves a FROM/JOIN alias bound in the query", () => {
    const sql = "SELECT  FROM store.customers c JOIN store.orders o ON c.id = o.id WHERE c.";
    expect(names(columnsForQualifier("c", TABLES, sql))).toEqual(["id", "email", "tier"]);
    expect(names(columnsForQualifier("o", TABLES, sql))).toEqual(["id", "total"]);
  });

  it("resolves an `AS` alias", () => {
    const sql = "SELECT * FROM store.customers AS cust WHERE cust.";
    expect(names(columnsForQualifier("cust", TABLES, sql))).toEqual(["id", "email", "tier"]);
  });

  it("returns null for an unknown qualifier (so the source-table fallback can run)", () => {
    expect(columnsForQualifier("nope", TABLES, "SELECT nope.")).toBeNull();
  });

  it("drops unnamed/blank columns so the widget never shows a blank row", () => {
    const withBlank = [
      { source: "memory", schema: "main", table: "augment", columns: ["side", "", "  ", "region"] },
    ] as unknown as TableInfo[];
    expect(names(columnsForQualifier("augment", withBlank, "SELECT augment."))).toEqual([
      "side", "region",
    ]);
  });
});
