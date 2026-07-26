import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { TableInfo } from "../api";
import SourceTree from "./SourceTree";

const t = (source: string, table: string): TableInfo => ({ source, schema: "main", table, columns: [] });

describe("SourceTree keyboard", () => {
  it("loads a table on Enter (keyboard-operable)", () => {
    const onPick = vi.fn();
    const src = {
      name: "store", type: "sqlite", path: "s.db", tables: ["customers"],
      pii: {}, connection: {}, has_credential: false,
    };
    render(
      <SourceTree
        sources={[src]}
        tables={[{ source: "store", schema: "main", table: "customers", columns: ["id"] }]}
        onPick={onPick}
      />,
    );
    fireEvent.keyDown(screen.getByText("customers"), { key: "Enter" });
    expect(onPick).toHaveBeenCalled();
  });
});

describe("SourceTree remove affordance", () => {
  it("offers remove on a snapshot and calls onRemove('snapshot', name)", () => {
    const onRemove = vi.fn();
    render(<SourceTree sources={[]} tables={[t("local", "snap")]} onPick={() => {}} onRemove={onRemove} />);
    fireEvent.click(screen.getByLabelText("Remove local.snap"));
    expect(onRemove).toHaveBeenCalledWith("snapshot", "snap");
  });

  it("offers remove on an upload and calls onRemove('upload', name)", () => {
    const onRemove = vi.fn();
    render(<SourceTree sources={[]} tables={[t("memory", "up")]} onPick={() => {}} onRemove={onRemove} />);
    fireEvent.click(screen.getByLabelText("Remove up"));
    expect(onRemove).toHaveBeenCalledWith("upload", "up");
  });

  it("column/table/source access toggles call onSetAccess with the right args", () => {
    const onSetAccess = vi.fn();
    const src = {
      name: "store", type: "sqlite", path: "s.db", tables: ["customers"],
      pii: {}, connection: {}, has_credential: false,
    };
    const tbl = {
      source: "store", schema: "main", table: "customers", columns: ["email", "tier"],
      access: { email: { masked: true, pii: true }, tier: { masked: false, pii: false } },
    };
    render(<SourceTree sources={[src]} tables={[tbl]} onPick={() => {}} onSetAccess={onSetAccess} />);

    // table-level: some column is real -> toggle masks all (value false)
    fireEvent.click(screen.getByLabelText("Toggle agent access for table customers"));
    expect(onSetAccess).toHaveBeenCalledWith({ source: "store", table: "customers", value: false });

    // source-level: same reasoning
    fireEvent.click(screen.getByLabelText("Toggle agent access for source store"));
    expect(onSetAccess).toHaveBeenCalledWith({ source: "store", value: false });

    // column-level: email is masked -> toggle turns it on (value true)
    fireEvent.click(screen.getByLabelText("Expand columns"));
    fireEvent.click(screen.getByLabelText("Toggle agent access for email"));
    expect(onSetAccess).toHaveBeenCalledWith({
      source: "store", table: "customers", column: "email", value: true,
    });
  });

  it("does not offer remove on a charter-source table", () => {
    const src = { name: "store", type: "sqlite", path: "s.db", tables: ["orders"], pii: {}, connection: {}, has_credential: false };
    render(<SourceTree sources={[src]} tables={[t("store", "orders")]} onPick={() => {}} onRemove={() => {}} />);
    expect(screen.queryByLabelText("Remove store.orders")).toBeNull();
  });
});
