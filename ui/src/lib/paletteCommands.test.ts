import { describe, expect, it, vi } from "vitest";
import { CORE_ACTION_IDS, buildPaletteCommands } from "./paletteCommands";

const handlers = {
  run: vi.fn(),
  cancel: vi.fn(),
  newQueryTab: vi.fn(),
  closeQueryTab: vi.fn(),
  nextPage: vi.fn(),
  prevPage: vi.fn(),
  exportResult: vi.fn(),
  exportAs: vi.fn(),
  snapshot: vi.fn(),
  profile: vi.fn(),
  explain: vi.fn(),
  estimate: vi.fn(),
  history: vi.fn(),
  goTab: vi.fn(),
  toggleAgentView: vi.fn(),
  toggleTheme: vi.fn(),
  help: vi.fn(),
  tour: vi.fn(),
  explore: vi.fn(),
  ask: vi.fn(),
  govern: vi.fn(),
  connectLlm: vi.fn(),
  loadDemo: vi.fn(),
  charterFiles: vi.fn(),
  addSource: vi.fn(),
  uploadFile: vi.fn(),
  saveQuery: vi.fn(),
  copyMarkdown: vi.fn(),
  copyLink: vi.fn(),
  copySql: vi.fn(),
  exportEvidence: vi.fn(),
  runDataTests: vi.fn(),
  disconnectAgent: vi.fn(),
};

describe("buildPaletteCommands", () => {
  it("includes every core action even on an empty catalog", () => {
    const cmds = buildPaletteCommands({ handlers, tables: [], metrics: [], queries: [] });
    const ids = cmds.map((c) => c.id);
    for (const id of CORE_ACTION_IDS) {
      expect(ids, `missing ${id}`).toContain(id);
    }
  });

  it("adds open/run commands for tables, metrics, and saved queries", () => {
    const cmds = buildPaletteCommands({
      handlers,
      tables: [{ source: "store", table: "orders" }],
      metrics: [{ name: "revenue", sql: "SELECT 1" }],
      queries: ["net_rev"],
      snapshots: ["snap"],
      uploads: ["dropped"],
      queryTabs: [{ id: "2", title: "Query 2" }],
    });
    const labels = cmds.map((c) => c.label);
    expect(labels).toContain("Open store.orders");
    expect(labels).toContain("Run metric: revenue");
    expect(labels).toContain("Open query net_rev");
    expect(labels).toContain("Recheck snapshot snap");
    expect(labels).toContain("Promote upload dropped");
    expect(labels).toContain("Go to Query 2");
  });
});
