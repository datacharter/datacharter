import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import GuidesEditor from "./GuidesEditor";

beforeEach(() => {
  globalThis.fetch = vi.fn(async (url: string, opts?: RequestInit) => {
    if (url.endsWith("/api/guides/suggestions"))
      return new Response(
        JSON.stringify({
          suggestions: [
            { kind: "filter", relation: "sales", text: "Queries on `sales` usually filter `refunded = false`", count: 4, total: 5 },
          ],
        }),
      );
    if (url.endsWith("/api/guides") && (!opts || opts.method === undefined || opts.method === "GET"))
      return new Response(
        JSON.stringify({ guides: [{ name: "overview", content: "hi" }], contexts: [] }),
      );
    return new Response(JSON.stringify({ saved: true }));
  }) as unknown as typeof fetch;
});

describe("GuidesEditor", () => {
  it("shows an existing guide and saves edits", async () => {
    render(<GuidesEditor />);
    await waitFor(() => expect(screen.getByDisplayValue("hi")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Save"));
    await waitFor(() =>
      expect(globalThis.fetch).toHaveBeenCalledWith(
        "/api/guides",
        expect.objectContaining({ method: "PUT" }),
      ),
    );
  });

  it("lists suggestions and adds one into the editor", async () => {
    render(<GuidesEditor />);
    await waitFor(() => expect(screen.getByText(/usually filter/)).toBeInTheDocument());
    fireEvent.click(screen.getByText("Add"));
    await waitFor(() =>
      expect((screen.getByLabelText("guide content") as HTMLTextAreaElement).value).toMatch(
        /refunded = false/,
      ),
    );
  });
});

describe("GuidesEditor CRUD affordances", () => {
  it("shows + New and Delete for an existing guide", async () => {
    render(<GuidesEditor />);
    await waitFor(() => expect(screen.getByLabelText("New guide")).toBeInTheDocument());
    await waitFor(() =>
      expect(screen.getByLabelText(/Delete guide/)).toBeInTheDocument(),
    );
  });

  it("+ New clears the editor for a fresh guide", async () => {
    render(<GuidesEditor />);
    await waitFor(() => expect(screen.getByLabelText("New guide")).toBeInTheDocument());
    screen.getByLabelText("New guide").click();
    await waitFor(() => expect(screen.getByLabelText("guide name")).toHaveValue(""));
    expect(screen.getByLabelText("guide content")).toHaveValue("");
  });
});
