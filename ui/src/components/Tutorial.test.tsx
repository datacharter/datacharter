import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import Tutorial from "./Tutorial";

const actions = () => ({
  loadAndRunExample: vi.fn(),
  showChart: vi.fn(),
  showProfile: vi.fn(),
  showView: vi.fn(),
  toggleAgentView: vi.fn(),
  runAgentExample: vi.fn(),
});

describe("Tutorial", () => {
  it("walks from the basics through the governance arc", () => {
    const a = actions();
    render(<Tutorial actions={a} onClose={vi.fn()} />);
    expect(screen.getByText("Query — live")).toBeInTheDocument();

    const titles: string[] = [];
    for (let i = 0; i < 10; i++) {
      fireEvent.click(screen.getByText("Next"));
      titles.push(screen.getByRole("heading", { level: 3 }).textContent ?? "");
    }
    expect(titles).toContain("Prove it happened");
    expect(titles).toContain("Rules in plain English");
    expect(titles).toContain("Measure it, don't trust it");
  });

  it("governance steps navigate to their panels", () => {
    const a = actions();
    render(<Tutorial actions={a} onClose={vi.fn()} />);
    for (let i = 0; i < 10; i++) {
      const btn = screen.queryByText("Open Audit");
      if (btn) {
        fireEvent.click(btn);
        break;
      }
      fireEvent.click(screen.getByText("Next"));
    }
    expect(a.showView).toHaveBeenCalledWith("audit");
  });
});
