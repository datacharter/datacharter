import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import QueryTabs from "./QueryTabs";

const TABS = [
  { id: "1", title: "Query 1" },
  { id: "2", title: "Query 2" },
];

describe("QueryTabs", () => {
  it("marks the active tab and switches on click", () => {
    const onSelect = vi.fn();
    render(
      <QueryTabs tabs={TABS} activeId="1" onSelect={onSelect} onNew={() => {}} onClose={() => {}} />,
    );
    expect(screen.getByRole("tab", { name: /Query 1/ })).toHaveAttribute("aria-selected", "true");
    fireEvent.click(screen.getByRole("tab", { name: /Query 2/ }));
    expect(onSelect).toHaveBeenCalledWith("2");
  });

  it("adds a tab and closes a non-last tab", () => {
    const onNew = vi.fn();
    const onClose = vi.fn();
    render(
      <QueryTabs tabs={TABS} activeId="1" onSelect={() => {}} onNew={onNew} onClose={onClose} />,
    );
    fireEvent.click(screen.getByLabelText("New query"));
    expect(onNew).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByLabelText("Close Query 2"));
    expect(onClose).toHaveBeenCalledWith("2");
  });
});
