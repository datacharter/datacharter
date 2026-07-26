import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import HelpModal from "./HelpModal";

describe("HelpModal", () => {
  it("closes on Escape (focus-trapped dialog)", () => {
    const onClose = vi.fn();
    const { container } = render(<HelpModal onClose={onClose} />);
    const dialog = container.querySelector(".help-modal") as HTMLElement;
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  it("closes on the × button", () => {
    const onClose = vi.fn();
    const { getByLabelText } = render(<HelpModal onClose={onClose} />);
    fireEvent.click(getByLabelText("Close"));
    expect(onClose).toHaveBeenCalled();
  });
});
