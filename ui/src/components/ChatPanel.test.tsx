import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Message } from "./ChatPanel";

describe("agent transcript query chip", () => {
  it("renders the agent's SQL with an Open in editor button", () => {
    const onOpenSql = vi.fn();
    const { getByText } = render(
      <Message
        msg={{ role: "assistant", text: "There are 90 orders.", tools: [{ tool: "query", sql: "SELECT count(*) FROM orders" }] }}
        onOpenSql={onOpenSql}
      />,
    );
    expect(getByText("SELECT count(*) FROM orders")).toBeTruthy();
    fireEvent.click(getByText("Open in editor"));
    expect(onOpenSql).toHaveBeenCalledWith("SELECT count(*) FROM orders");
  });

  it("shows non-query tools as plain labels (no button)", () => {
    const { queryByText, getByText } = render(
      <Message msg={{ role: "assistant", text: "ok", tools: [{ tool: "list_tables", sql: "" }] }} />,
    );
    expect(getByText(/list_tables/)).toBeTruthy();
    expect(queryByText("Open in editor")).toBeNull();
  });
});

describe("verifiable-answer receipt", () => {
  const withReceipt = {
    role: "assistant" as const,
    text: "3 customers.",
    tools: [],
    receipt: { content_hash: "deadbeefcafe0000", signature: { key_id: "k1" }, body: {} },
  };

  it("shows the receipt affordance only when a receipt is present", () => {
    const { getByText } = render(<Message msg={withReceipt} />);
    expect(getByText("🔏 Verifiable answer")).toBeTruthy();
    expect(getByText("Download receipt")).toBeTruthy();
  });

  it("has no affordance without a receipt", () => {
    const { queryByText } = render(
      <Message msg={{ role: "assistant", text: "3 customers.", tools: [] }} />,
    );
    expect(queryByText("Download receipt")).toBeNull();
  });

  it("downloads the receipt JSON on click", () => {
    const createURL = vi.fn(() => "blob:x");
    const revokeURL = vi.fn();
    (URL as unknown as { createObjectURL: unknown }).createObjectURL = createURL;
    (URL as unknown as { revokeObjectURL: unknown }).revokeObjectURL = revokeURL;
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const { getByText } = render(<Message msg={withReceipt} />);
    fireEvent.click(getByText("Download receipt"));
    expect(createURL).toHaveBeenCalled();
    expect(click).toHaveBeenCalled();
    click.mockRestore();
  });
});
