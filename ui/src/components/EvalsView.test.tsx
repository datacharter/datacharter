import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import EvalsView from "./EvalsView";

beforeEach(() => {
  globalThis.fetch = vi.fn(async (url: string) => {
    if (url.endsWith("/api/evals"))
      return new Response(
        JSON.stringify({ suites: [{ name: "analytics", cases: [{ question: "q1" }] }] }),
      );
    if (url.endsWith("/api/evals/history")) return new Response(JSON.stringify({ runs: [] }));
    return new Response("{}");
  }) as unknown as typeof fetch;
});

describe("EvalsView", () => {
  it("lists suites and their cases", async () => {
    render(<EvalsView />);
    await waitFor(() => expect(screen.getByText("analytics")).toBeInTheDocument());
    expect(screen.getByText("q1")).toBeInTheDocument();
  });
});
