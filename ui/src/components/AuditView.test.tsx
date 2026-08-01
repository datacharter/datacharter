import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AuditView from "./AuditView";

beforeEach(() => {
  globalThis.fetch = vi.fn(async (url: string) => {
    if (url.endsWith("/api/audit"))
      return new Response(
        JSON.stringify({
          sessions: [],
          entries: [
            {
              seq: 1, ts: "2026-08-01T12:00:00Z", type: "session", session: "s1",
              surface: "mcp", user: "rishi", client: { name: "cursor", version: "1" },
            },
            {
              seq: 2, ts: "2026-08-01T12:00:05Z", type: "access", session: "s1",
              tool: "query", sql: "SELECT email FROM crm", row_count: 3,
              masked_columns: ["email"], error: null,
            },
          ],
        }),
      );
    return new Response(JSON.stringify({ ok: true, entries: 2, detail: "2 entries verified" }));
  }) as unknown as typeof fetch;
});

describe("AuditView", () => {
  it("renders the chain badge and a session with its access", async () => {
    render(<AuditView />);
    await waitFor(() => expect(screen.getByText(/chain verified/)).toBeInTheDocument());
    expect(screen.getByText("cursor")).toBeInTheDocument();
    expect(screen.getByText(/SELECT email FROM crm/)).toBeInTheDocument();
    expect(screen.getByText(/masked: email/)).toBeInTheDocument();
  });
});
