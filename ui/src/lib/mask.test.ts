import { describe, expect, it } from "vitest";
import { exportRequest, withoutColumns } from "./mask";

const result = {
  columns: ["id", "email", "tier"],
  rows: [
    [1, "a@x.com", "pro"],
    [2, "b@x.com", "free"],
  ],
  row_count: 2,
  truncated: false,
};

describe("withoutColumns", () => {
  it("drops named columns and their cells, preserves others", () => {
    const r = withoutColumns(result as never, new Set(["email"]));
    expect(r.columns).toEqual(["id", "tier"]);
    expect(r.rows).toEqual([
      [1, "pro"],
      [2, "free"],
    ]);
  });
  it("is case-insensitive; no-op when nothing matches", () => {
    expect(withoutColumns(result as never, new Set(["EMAIL"])).columns).toEqual(["id", "tier"]);
    expect(withoutColumns(result as never, new Set(["nope"])).columns).toEqual([
      "id",
      "email",
      "tier",
    ]);
  });
});

describe("exportRequest", () => {
  const masked = new Set(["email"]);
  const cols = ["id", "email", "tier"];
  it("masks + flags agent_view when on and a masked column is present", () => {
    const p = exportRequest("SELECT * FROM t", "csv", true, masked, cols);
    expect(p.body).toEqual({
      sql: "SELECT * FROM t", format: "csv", mask_columns: ["email"], agent_view: true,
    });
    expect(p.filename).toBe("datacharter-export-agent-view.csv");
  });
  it("plain request when agent view is off", () => {
    const p = exportRequest("SELECT * FROM t", "csv", false, masked, cols);
    expect(p.body).toEqual({ sql: "SELECT * FROM t", format: "csv" });
    expect(p.filename).toBe("datacharter-export.csv");
  });
  it("still flags agent_view (server applies the PII floor) even with no client mask", () => {
    // The server unions the charter PII, so the flag must survive an empty
    // client mask list — otherwise a missed column exports raw.
    const p = exportRequest("SELECT id FROM t", "json", true, masked, ["id", "tier"]);
    expect(p.body).toEqual({
      sql: "SELECT id FROM t", format: "json", mask_columns: [], agent_view: true,
    });
    expect(p.filename).toBe("datacharter-export-agent-view.json");
  });
});
