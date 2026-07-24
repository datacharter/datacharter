import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useMemo, useRef, useState } from "react";
import type { QueryResult } from "../api";

const helper = createColumnHelper<unknown[]>();
const ROW_HEIGHT = 27;
const MASKED = "•••";

/** Virtualized grid: only visible rows hit the DOM, so it scrolls a 10k cap smoothly.
 *  With `maskColumns`, PII columns render as ••• — what the agent / MCP server see. */
export default function ResultsGrid({
  result,
  maskColumns,
}: {
  result: QueryResult;
  maskColumns?: Set<string>;
}) {
  const [sorting, setSorting] = useState<{ id: string; desc: boolean }[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  const maskIdx = useMemo(
    () =>
      new Set(
        result.columns
          .map((name, i) => (maskColumns?.has(name.toLowerCase()) ? i : -1))
          .filter((i) => i >= 0),
      ),
    [result.columns, maskColumns],
  );

  const columns = useMemo(
    () =>
      result.columns.map((name, i) =>
        helper.accessor((row) => row[i], {
          id: name || `col_${i}`,
          header: name,
          cell: (info) => (maskIdx.has(i) ? MASKED : formatCell(info.getValue())),
        }),
      ),
    [result.columns, maskIdx],
  );

  // One pass over the data to pin each column to its content width — keeps
  // columns stable while virtualized (auto-sizing can't, it only sees a window).
  const widths = useMemo(() => measureWidths(result), [result]);

  const table = useReactTable({
    data: result.rows,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  const rows = table.getRowModel().rows;
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 16,
  });
  const items = virtualizer.getVirtualItems();
  const padTop = items.length ? items[0].start : 0;
  const padBottom = items.length ? virtualizer.getTotalSize() - items[items.length - 1].end : 0;
  const numWidth = Math.max(46, String(rows.length).length * 9 + 22);
  const totalWidth = numWidth + widths.reduce((a, b) => a + b, 0);

  return (
    <div className="grid-wrap">
      <div className="grid-scroll" ref={scrollRef}>
        <table className="grid" style={{ tableLayout: "fixed", width: totalWidth }}>
          <colgroup>
            <col style={{ width: numWidth }} />
            {widths.map((w, i) => (
              <col key={i} style={{ width: w }} />
            ))}
          </colgroup>
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                <th className="rownum">#</th>
                {hg.headers.map((h) => (
                  <th key={h.id} onClick={h.column.getToggleSortingHandler()}>
                    {flexRender(h.column.columnDef.header, h.getContext())}
                    {{ asc: " ↑", desc: " ↓" }[h.column.getIsSorted() as string] ?? ""}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {padTop > 0 && <tr style={{ height: padTop }} />}
            {items.map((vi) => {
              const row = rows[vi.index];
              return (
                <tr key={row.id} style={{ height: ROW_HEIGHT }}>
                  <td className="rownum">{vi.index + 1}</td>
                  {row.getVisibleCells().map((cell, ci) => {
                    const numeric = !maskIdx.has(ci) && typeof cell.getValue() === "number";
                    return (
                      <td key={cell.id} className={numeric ? "num" : undefined}>
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
            {padBottom > 0 && <tr style={{ height: padBottom }} />}
          </tbody>
        </table>
      </div>
      <div className="status">
        {result.row_count.toLocaleString()} rows
        {result.truncated ? " (truncated — refine your query or raise the limit)" : ""}
      </div>
      {result.warnings?.map((warning) => (
        <div key={warning} className="warning" role="alert">
          {warning}
        </div>
      ))}
      {result.provenance && result.provenance.relations.length > 0 && (
        <div className="provenance" title={result.provenance.columns.join(", ")}>
          Reads {result.provenance.relations.join(", ")}
        </div>
      )}
      {maskIdx.size > 0 && (
        <div className="agent-view-note">
          Agent view — {maskIdx.size} PII column{maskIdx.size > 1 ? "s" : ""} masked (what the
          agent and MCP server see).
        </div>
      )}
    </div>
  );
}

/** Per-column pixel width from the widest value (header included), clamped. */
function measureWidths(result: QueryResult): number[] {
  return result.columns.map((name, i) => {
    let longest = String(name).length;
    for (const row of result.rows) {
      const value = row[i];
      const len = value == null ? 1 : String(value).length;
      if (len > longest) longest = len;
    }
    return Math.min(400, Math.max(64, longest * 7.5 + 26));
  });
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "∅";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
