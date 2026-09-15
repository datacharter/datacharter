import { describe, expect, it } from "vitest";
import type { QueryResult } from "../api";
import { resultToMarkdown } from "./resultMarkdown";

const result: QueryResult = {
  columns: ["who", "contact"],
  rows: [
    ["ada", "ada@example.com"],
    ["grace", "a | b"],
  ],
  row_count: 2,
  truncated: false,
  provenance: { relations: ["store.customers"], columns: ["who", "contact"] },
};

describe("resultToMarkdown", () => {
  it("builds a fenced SQL block, a table, and a provenance footer", () => {
    const md = resultToMarkdown("SELECT * FROM store.customers", result);
    expect(md).toContain("```sql\nSELECT * FROM store.customers\n```");
    expect(md).toContain("| who | contact |");
    expect(md).toContain("| ada | ada@example.com |");
    expect(md).toContain("a \\| b");
    expect(md).toContain("_Reads store.customers · 2 rows · DataCharter_");
  });

  it("masks PII columns", () => {
    const md = resultToMarkdown("SELECT 1", result, { maskColumns: new Set(["contact"]) });
    expect(md).toContain("| ada | ••• |");
    expect(md).not.toContain("ada@example.com");
  });

  it("caps rows and notes how many were omitted", () => {
    const big: QueryResult = {
      ...result,
      rows: Array.from({ length: 5 }, (_, i) => [`r${i}`, "x"]),
      row_count: 5,
    };
    const md = resultToMarkdown("SELECT 1", big, { maxRows: 2 });
    expect(md).toContain("| r0 | x |");
    expect(md).toContain("| r1 | x |");
    expect(md).not.toContain("| r2 |");
    expect(md).toContain("… 3 more rows");
  });
});
