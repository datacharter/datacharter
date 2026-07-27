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
