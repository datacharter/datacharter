import { describe, expect, it } from "vitest";
import { shouldAutoScroll } from "./chatScroll";

describe("shouldAutoScroll", () => {
  it("pins when already at/near the bottom", () => {
    expect(shouldAutoScroll(920, 1000, 80)).toBe(true); // exactly at bottom
    expect(shouldAutoScroll(880, 1000, 80)).toBe(true); // within threshold
  });
  it("leaves a scrolled-up reader alone", () => {
    expect(shouldAutoScroll(100, 1000, 80)).toBe(false);
  });
});
