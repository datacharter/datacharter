import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CharterStudio from "./CharterStudio";

const CHARTER = {
  yaml: "version: 1\nsources:\n  store:\n    pii:\n      customers: [email]\n",
  sources: [
    {
      name: "store",
      tables: ["customers"],
      pii: { customers: ["email"] },
      row_filters: { customers: "" },
    },
  ],
  policies: { "store.customers": ["aggregates only"] },
};

const TABLES = {
  tables: [
    {
      source: "store",
      schema: "main",
      table: "customers",
      columns: ["id", "email", "tier"],
      access: {},
    },
  ],
};

beforeEach(() => {
  globalThis.fetch = vi.fn(async (url: string, opts?: RequestInit) => {
    if (url.endsWith("/api/charter") && (!opts || !opts.method || opts.method === "GET")) {
      return new Response(JSON.stringify(CHARTER));
    }
    if (url.endsWith("/api/tables")) return new Response(JSON.stringify(TABLES));
    if (url.endsWith("/api/charter/studio")) {
      return new Response(JSON.stringify({ saved: true }));
    }
    return new Response("{}");
  }) as unknown as typeof fetch;
});

describe("CharterStudio", () => {
  it("shows PII checkboxes, a row filter, policies, and the YAML pane", async () => {
    render(<CharterStudio />);
    expect(await screen.findByText("store.customers")).toBeInTheDocument();
    expect(screen.getByLabelText("email")).toBeChecked();
    expect(screen.getByLabelText("id")).not.toBeChecked();
    expect(screen.getByLabelText("Aggregates only")).toBeChecked();
    expect(screen.getByLabelText("charter.yaml")).toHaveTextContent("pii:");
  });

  it("saves a PII toggle as a replace, not a merge", async () => {
    render(<CharterStudio />);
    await screen.findByText("store.customers");
    fireEvent.click(screen.getByLabelText("email"));
    fireEvent.click(screen.getByText("Save charter"));
    await waitFor(() =>
      expect(globalThis.fetch).toHaveBeenCalledWith(
        "/api/charter/studio",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    const calls = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls;
    const save = calls.find((c) => String(c[0]).endsWith("/api/charter/studio"));
    const body = JSON.parse(String(save?.[1]?.body));
    expect(body.pii[0].columns).toEqual([]);
  });
});
