import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

// Vega needs canvas; stub it so we can assert on the controls only.
vi.mock("vega-embed", () => ({
  default: () => Promise.resolve({ view: { finalize() {} } }),
}));

import ChartPanel from "./ChartPanel";

const result = {
  columns: ["email", "region", "spend"],
  rows: [
    ["a@x.com", "us", 10],
    ["b@x.com", "eu", 20],
  ],
  row_count: 2,
  truncated: false,
};

describe("ChartPanel agent view", () => {
  it("omits masked columns from the axis options", () => {
    const { container } = render(
      <ChartPanel result={result as never} maskColumns={new Set(["email"])} />,
    );
    const opts = Array.from(container.querySelectorAll("select")).flatMap((s) =>
      Array.from(s.options).map((o) => o.value),
    );
    expect(opts).not.toContain("email");
    expect(opts).toContain("region");
    expect(opts).toContain("spend");
  });
});
