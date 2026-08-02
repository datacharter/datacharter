import { describe, expect, it } from "vitest";

import type { QueryResult } from "../api";
import { applicableKinds, detectChart } from "./chartSpec";

const result = (columns: string[], rows: unknown[][]): QueryResult =>
  ({ columns, rows, row_count: rows.length, truncated: false, warnings: [] }) as QueryResult;

describe("applicableKinds", () => {
  it("all-numeric result still offers bar/line/area (not just scatter)", () => {
    const kinds = applicableKinds(
      result(["customer_id", "orders", "revenue"], [[1, 30, 900.5], [2, 30, 850.0]]),
    );
    expect(kinds).toEqual(expect.arrayContaining(["bar", "line", "area", "scatter"]));
  });
  it("categorical + numeric adds pie", () => {
    const kinds = applicableKinds(result(["tier", "n"], [["pro", 2], ["free", 1]]));
    expect(kinds).toContain("pie");
  });
  it("single numeric column alone -> nothing to chart", () => {
    expect(applicableKinds(result(["n"], [[1], [2]]))).toEqual([]);
  });
});

describe("detectChart", () => {
  it("categorical + numeric -> bar", () =>
    expect(detectChart(result(["tier", "n"], [["pro", 2]]))?.kind).toBe("bar"));
  it("two numerics -> scatter", () =>
    expect(detectChart(result(["a", "b"], [[1, 2]]))?.kind).toBe("scatter"));
});
