import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import CommandPalette from "./CommandPalette";

const cmds = (run: () => void) => [
  { id: "run", label: "Run", run },
  { id: "exp", label: "Export", run: () => {} },
];

describe("CommandPalette", () => {
  it("filters, runs the top match on Enter, and closes", () => {
    const run = vi.fn();
    const onClose = vi.fn();
    const { getByPlaceholderText } = render(
      <CommandPalette commands={cmds(run)} onClose={onClose} />,
    );
    const input = getByPlaceholderText(/type a command/i);
    fireEvent.change(input, { target: { value: "run" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(run).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it("closes on Escape", () => {
    const onClose = vi.fn();
    const { getByPlaceholderText } = render(
      <CommandPalette commands={cmds(() => {})} onClose={onClose} />,
    );
    fireEvent.keyDown(getByPlaceholderText(/type a command/i), { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  it("runs a command on click", () => {
    const run = vi.fn();
    const onClose = vi.fn();
    const { getByText } = render(<CommandPalette commands={cmds(run)} onClose={onClose} />);
    fireEvent.click(getByText("Run"));
    expect(run).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });
});
