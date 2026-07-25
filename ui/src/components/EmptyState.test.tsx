import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import EmptyState from "./EmptyState";

const noop = () => {};
const noopAsync = async () => {};

describe("EmptyState", () => {
  it("renders the three onboarding actions", () => {
    render(<EmptyState onAddSource={noop} onUpload={noop} onLoadDemo={noopAsync} />);
    expect(screen.getByText("+ Add a source")).toBeInTheDocument();
    expect(screen.getByText("Drop a CSV")).toBeInTheDocument();
    expect(screen.getByText("Load the demo dataset")).toBeInTheDocument();
  });

  it("'+ Add a source' fires its handler", () => {
    const onAddSource = vi.fn();
    render(<EmptyState onAddSource={onAddSource} onUpload={noop} onLoadDemo={noopAsync} />);
    fireEvent.click(screen.getByText("+ Add a source"));
    expect(onAddSource).toHaveBeenCalledOnce();
  });

  it("'Load the demo dataset' calls onLoadDemo and shows a pending state", async () => {
    const onLoadDemo = vi.fn(() => new Promise<void>(() => {})); // never resolves
    render(<EmptyState onAddSource={noop} onUpload={noop} onLoadDemo={onLoadDemo} />);
    fireEvent.click(screen.getByText("Load the demo dataset"));
    expect(onLoadDemo).toHaveBeenCalledOnce();
    expect(await screen.findByText("Loading…")).toBeInTheDocument();
  });
});
