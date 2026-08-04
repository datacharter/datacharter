import { render } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import type { QueryResult } from "../api";
import ResultsGrid from "./ResultsGrid";

// jsdom has no layout: the virtualizer measures a 0-height scroller and renders
// zero rows. Give every element a real-looking box so rows materialize.
beforeAll(() => {
  class RO {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  globalThis.ResizeObserver = globalThis.ResizeObserver ?? (RO as never);
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue({
    x: 0, y: 0, top: 0, left: 0, bottom: 800, right: 800,
    width: 800, height: 800, toJSON: () => ({}),
  } as DOMRect);
  // the virtualizer sizes from offsetWidth/offsetHeight, which jsdom fixes at 0
  Object.defineProperty(HTMLElement.prototype, "offsetHeight", {
    configurable: true,
    get: () => 800,
  });
  Object.defineProperty(HTMLElement.prototype, "offsetWidth", {
    configurable: true,
    get: () => 800,
  });
});

const RESULT: QueryResult = {
  columns: ["who", "contact"],
  rows: [
    ["ada", "ada@example.com"],
    ["grace", "grace@example.com"],
  ],
  row_count: 2,
  truncated: false,
};

describe("ResultsGrid agent-view masking", () => {
  it("renders ••• for masked columns and real values for the rest", async () => {
    const { queryByText, findAllByText, findByText } = render(
      <ResultsGrid result={RESULT} maskColumns={new Set(["contact"])} />,
    );
    expect(await findByText("ada")).toBeTruthy();
    expect((await findAllByText("•••")).length).toBe(2);
    // The raw value must not exist ANYWHERE in the DOM — masking that merely
    // hides visually would still leak to copy/inspect.
    expect(queryByText("ada@example.com")).toBeNull();
  });

  it("matches mask columns case-insensitively", () => {
    const { queryByText } = render(
      <ResultsGrid
        result={{ ...RESULT, columns: ["who", "Contact"] }}
        maskColumns={new Set(["contact"])}
      />,
    );
    expect(queryByText("ada@example.com")).toBeNull();
  });

  it("renders everything real without maskColumns", async () => {
    const { findByText, queryByText } = render(<ResultsGrid result={RESULT} />);
    expect(await findByText("ada@example.com")).toBeTruthy();
    expect(queryByText("•••")).toBeNull();
  });
});
