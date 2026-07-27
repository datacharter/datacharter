import { render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import HistoryPanel from "./HistoryPanel";

function stubHistory(entries: unknown[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify({ entries }), { status: 200 })),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("HistoryPanel", () => {
  it("renders entries and picks one on click", async () => {
    stubHistory([{ ts: new Date().toISOString(), sql: "SELECT 1", row_count: 3, relations: [], columns: [] }]);
    const onPick = vi.fn();
    const onClose = vi.fn();
    const { findByText } = render(<HistoryPanel onPick={onPick} onClose={onClose} />);
    const item = await findByText("SELECT 1");
    item.closest("button")!.click();
    expect(onPick).toHaveBeenCalledWith("SELECT 1");
    expect(onClose).toHaveBeenCalled();
  });

  it("shows an empty state when there is no history", async () => {
    stubHistory([]);
    const { findByText } = render(<HistoryPanel onPick={vi.fn()} onClose={vi.fn()} />);
    await waitFor(() => expect(findByText(/No queries yet/)).resolves.toBeTruthy());
  });
});
