import { describe, expect, it } from "vitest";
import { type Command, fuzzyFilter } from "./commandPalette";

const cmd = (label: string): Command => ({ id: label, label, run: () => {} });
const labels = (cs: Command[]) => cs.map((c) => c.label);

describe("fuzzyFilter", () => {
  const cmds = [cmd("Run"), cmd("Export"), cmd("Open store.orders"), cmd("Toggle theme")];

  it("returns everything for an empty query", () => {
    expect(fuzzyFilter(cmds, "")).toHaveLength(4);
  });
  it("matches a subsequence, case-insensitively", () => {
    expect(labels(fuzzyFilter(cmds, "ordr"))).toContain("Open store.orders");
  });
  it("drops non-matches", () => {
    expect(fuzzyFilter(cmds, "zzz")).toHaveLength(0);
  });
  it("ranks a prefix hit above a scattered hit", () => {
    const res = labels(fuzzyFilter([cmd("Toggle theme"), cmd("Export")], "e"));
    expect(res[0]).toBe("Export"); // prefix 'E' beats scattered 'e' in "Toggle theme"
  });
});
