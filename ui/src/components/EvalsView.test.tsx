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
    if (url.endsWith("/api/evals/files"))
      return new Response(
        JSON.stringify({ files: [{ name: "analytics", content: "version: 1\ncases: []\n" }] }),
      );
    if (url.endsWith("/api/tests/run"))
      return new Response(
        JSON.stringify({
          results: [
            { name: "orders_not_empty", passed: true },
            { name: "no_null_emails", passed: false, failing_rows: 3 },
          ],
          passed: false,
        }),
      );
    return new Response("{}");
  }) as unknown as typeof fetch;
});

describe("EvalsView", () => {
  it("lists suites and their cases", async () => {
    render(<EvalsView />);
    await waitFor(() => expect(screen.getAllByText("analytics").length).toBeGreaterThan(0));
    expect(screen.getByText("q1")).toBeInTheDocument();
  });

  it("loads a suite into the editor and offers Save/Delete", async () => {
    render(<EvalsView />);
    await waitFor(() =>
      expect(screen.getByLabelText("suite yaml")).toHaveValue("version: 1\ncases: []\n"),
    );
    expect(screen.getByLabelText("suite name")).toHaveValue("analytics");
    expect(screen.getByText("Save")).toBeInTheDocument();
    expect(screen.getByLabelText("Delete suite analytics")).toBeInTheDocument();
  });

  it("+ New starts a template suite", async () => {
    render(<EvalsView />);
    await waitFor(() => expect(screen.getByLabelText("New eval suite")).toBeInTheDocument());
    screen.getByLabelText("New eval suite").click();
    await waitFor(() => expect(screen.getByLabelText("suite name")).toHaveValue(""));
    expect((screen.getByLabelText("suite yaml") as HTMLTextAreaElement).value).toContain(
      "cases:",
    );
  });

  it("runs data tests and shows per-test verdicts", async () => {
    render(<EvalsView />);
    await waitFor(() => expect(screen.getByLabelText("Run data tests")).toBeInTheDocument());
    screen.getByLabelText("Run data tests").click();
    await waitFor(() => expect(screen.getByText(/orders_not_empty/)).toBeInTheDocument());
    expect(screen.getByText(/3 failing row/)).toBeInTheDocument();
  });
});
