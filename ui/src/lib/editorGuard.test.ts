import { describe, expect, it } from "vitest";
import { shouldReplaceEditor } from "./editorGuard";

describe("shouldReplaceEditor", () => {
  it("replaces an empty editor", () => {
    expect(shouldReplaceEditor("", "SELECT 1")).toBe(true);
    expect(shouldReplaceEditor("   \n ", "SELECT 1")).toBe(true);
  });
  it("replaces when unchanged from the last loaded value", () => {
    expect(shouldReplaceEditor("SELECT * FROM t", "SELECT * FROM t")).toBe(true);
  });
  it("preserves in-progress (dirty) SQL", () => {
    expect(shouldReplaceEditor("SELECT custom", "SELECT * FROM t")).toBe(false);
  });
});
