import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import Toast from "./Toast";

describe("Toast", () => {
  it("shows the message and closes on ✕", () => {
    const onClose = vi.fn();
    const { getByText, getByLabelText } = render(
      <Toast message="Export failed" onClose={onClose} />,
    );
    expect(getByText("Export failed")).toBeTruthy();
    fireEvent.click(getByLabelText("Dismiss"));
    expect(onClose).toHaveBeenCalled();
  });

  it("auto-dismisses after the timeout", () => {
    vi.useFakeTimers();
    try {
      const onClose = vi.fn();
      render(<Toast message="x" onClose={onClose} timeoutMs={6000} />);
      expect(onClose).not.toHaveBeenCalled();
      vi.advanceTimersByTime(6000);
      expect(onClose).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });
});
