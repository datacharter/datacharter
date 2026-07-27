import { describe, expect, it } from "vitest";
import { formatEstimate } from "./estimate";

describe("formatEstimate", () => {
  it("formats a row estimate", () => {
    expect(formatEstimate(200)).toEqual({ label: "~200 rows", warn: false });
  });

  it("warns above the threshold", () => {
    expect(formatEstimate(2_000_000).warn).toBe(true);
  });

  it("handles a missing estimate", () => {
    expect(formatEstimate(null)).toEqual({ label: "no estimate", warn: false });
  });
});
