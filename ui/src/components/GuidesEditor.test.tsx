import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import GuidesEditor from "./GuidesEditor";

beforeEach(() => {
  globalThis.fetch = vi.fn(async (url: string, opts?: RequestInit) => {
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
});
