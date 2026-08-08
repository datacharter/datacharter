import { describe, expect, it } from "vitest";

import { makeEpoch, shouldPreview } from "./queryLifecycle";

describe("makeEpoch", () => {
  it("only the newest token is current — the exact race guard", () => {
    const e = makeEpoch();
    const run = e.next(); // Run fires
    const preview = e.next(); // a later preview fires after it
    // Run's response lands last but is stale, so it must be dropped:
    expect(e.isCurrent(run)).toBe(false);
    expect(e.isCurrent(preview)).toBe(true);
  });

  it("a stale preview response is ignored once Run supersedes it", () => {
    const e = makeEpoch();
    const preview = e.next(); // preview fires first
    const run = e.next(); // Run fires, invalidating the preview
    expect(e.isCurrent(preview)).toBe(false); // late preview response → dropped
    expect(e.isCurrent(run)).toBe(true); // Run's full result wins
  });

  it("tokens increase monotonically from 1", () => {
    const e = makeEpoch();
    expect(e.next()).toBe(1);
    expect(e.next()).toBe(2);
    expect(e.next()).toBe(3);
  });
});

describe("shouldPreview", () => {
  it("previews normal edited SQL", () => {
    expect(shouldPreview("SELECT 1", null, false)).toBe(true);
  });

  it("does not preview empty or comment-only SQL", () => {
    expect(shouldPreview("", null, false)).toBe(false);
    expect(shouldPreview("   ", null, false)).toBe(false);
    expect(shouldPreview("-- just a comment", null, false)).toBe(false);
  });

  it("does not preview while a Run is in flight", () => {
    expect(shouldPreview("SELECT 1", null, true)).toBe(false);
  });

  it("does not preview SQL identical to the last Run (ignoring comments)", () => {
    expect(shouldPreview("SELECT 1", "SELECT 1", false)).toBe(false);
    expect(shouldPreview("SELECT 1 -- note", "SELECT 1", false)).toBe(false);
    expect(shouldPreview("  SELECT 1  ", "SELECT 1", false)).toBe(false);
  });

  it("previews when the SQL body differs from the last Run", () => {
    expect(shouldPreview("SELECT 2", "SELECT 1", false)).toBe(true);
  });
});
