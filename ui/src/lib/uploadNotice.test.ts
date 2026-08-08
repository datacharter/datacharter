import { describe, expect, it } from "vitest";

import { uploadNotice } from "./uploadNotice";

describe("uploadNotice", () => {
  it("returns null when no PII was detected", () => {
    expect(uploadNotice("orders", [])).toBeNull();
  });

  it("names the table, the columns, and points at Agent view", () => {
    const msg = uploadNotice("people", ["email", "phone"]);
    expect(msg).toContain("people");
    expect(msg).toContain("email, phone");
    expect(msg).toContain("Agent view");
    expect(msg).toContain("•••");
  });

  it("handles a single column", () => {
    expect(uploadNotice("leads", ["email"])).toContain("PII detected in leads: email");
  });
});
