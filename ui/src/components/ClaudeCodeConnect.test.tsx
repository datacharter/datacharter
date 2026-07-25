import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ClaudeCodeConnect from "./ClaudeCodeConnect";

const status = (over = {}) => ({
  available: false, model: null, base_url: null, has_key: false,
  backend: "llm", claude_code_available: true, ...over,
});

afterEach(() => vi.restoreAllMocks());

describe("ClaudeCodeConnect", () => {
  it("is hidden when Claude Code is unavailable", () => {
    const { container } = render(
      <ClaudeCodeConnect status={status({ claude_code_available: false })} onDone={() => {}} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("offers connect when available and idle", () => {
    render(<ClaudeCodeConnect status={status()} onDone={() => {}} />);
    expect(screen.getByText(/Connect Claude Code/)).toBeInTheDocument();
  });

  it("connects on click and calls onDone", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ backend: "claude-code" }), { status: 200 }),
    );
    const onDone = vi.fn();
    render(<ClaudeCodeConnect status={status()} onDone={onDone} />);
    fireEvent.click(screen.getByText(/Connect Claude Code/));
    await waitFor(() => expect(onDone).toHaveBeenCalledOnce());
  });

  it("shows the governance refusal message on failure", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ error: { type: "governance", message: "exposes non-governed tools: Bash" } }), { status: 400 }),
    );
    render(<ClaudeCodeConnect status={status()} onDone={() => {}} />);
    fireEvent.click(screen.getByText(/Connect Claude Code/));
    expect(await screen.findByText(/non-governed tools: Bash/)).toBeInTheDocument();
  });

  it("shows active state + switch-back when connected", () => {
    render(<ClaudeCodeConnect status={status({ backend: "claude-code" })} onDone={() => {}} />);
    expect(screen.getByText(/Agent: Claude Code/)).toBeInTheDocument();
    expect(screen.getByText(/Switch to API LLM/)).toBeInTheDocument();
  });
});
