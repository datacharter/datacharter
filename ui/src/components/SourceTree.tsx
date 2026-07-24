import { useMemo, useState } from "react";
import type { SourceInfo, TableInfo } from "../api";

interface Props {
  sources: SourceInfo[];
  tables: TableInfo[];
  onPick: (relation: string) => void;
}

const FILE_TYPES = ["csv", "parquet", "json", "iceberg", "delta"];

/** Top-level group: DBs by engine type, files by storage backend (s3/gcs/azure/files). */
function systemLabel(s: SourceInfo): string {
  if (FILE_TYPES.includes(s.type)) {
    const p = s.path ?? "";
    if (p.startsWith("s3://")) return "s3";
    if (p.startsWith("gs://") || p.startsWith("gcs://")) return "gcs";
    if (p.startsWith("azure://") || p.startsWith("az://")) return "azure";
    return "files";
  }
  return s.type;
}

/** Sidebar catalog: system → source (contract) → tables → columns. Sources expand by
 *  default; tables expand on the +/- to reveal columns. Clicking a name inserts a query. */
export default function SourceTree({ sources, tables, onPick }: Props) {
  const [collapsedSources, setCollapsedSources] = useState<Set<string>>(new Set());
  const [openTables, setOpenTables] = useState<Set<string>>(new Set());

  const toggle = (set: Set<string>, key: string) => {
    const next = new Set(set);
    next.has(key) ? next.delete(key) : next.add(key);
    return next;
  };

  const bySource = useMemo(() => {
    const map = new Map<string, TableInfo[]>();
    for (const t of tables) {
      map.set(t.source, [...(map.get(t.source) ?? []), t]);
    }
    return map;
  }, [tables]);

  const piiFor = (source: SourceInfo, table: string) =>
    (source.pii[table] ?? source.pii[source.name] ?? []).length > 0;

  const tablesFor = (s: SourceInfo): TableInfo[] =>
    bySource.get(s.name) ?? (bySource.get("memory") ?? []).filter((t) => t.table === s.name);

  const systems = useMemo(() => {
    const map = new Map<string, SourceInfo[]>();
    for (const s of sources) map.set(systemLabel(s), [...(map.get(systemLabel(s)) ?? []), s]);
    return [...map.entries()];
  }, [sources]);

  const locals = bySource.get("local") ?? [];
  const owned = new Set(sources.map((s) => s.name));
  const uploads = (bySource.get("memory") ?? []).filter((t) => !owned.has(t.table));

  const tableNode = (t: TableInfo, relation: string, source?: SourceInfo) => {
    const open = openTables.has(relation);
    const hasCols = t.columns.length > 0;
    return (
      <div key={relation}>
        <div className="tree-table">
          <button
            type="button"
            className={hasCols ? "tree-ex" : "tree-ex tree-ex-leaf"}
            onClick={() => hasCols && setOpenTables((s) => toggle(s, relation))}
            aria-label={hasCols ? (open ? "Collapse columns" : "Expand columns") : undefined}
          >
            {hasCols ? (open ? "−" : "+") : ""}
          </button>
          <span className="tree-table-name" onClick={() => onPick(relation)}>
            {t.table}
          </span>
          {source && piiFor(source, t.table) && <span className="pii">PII</span>}
        </div>
        {open && (
          <div className="tree-columns">
            {t.columns.map((c) => (
              <div className="tree-column" key={c} onClick={() => onPick(relation)}>
                {c}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  const sourceNode = (source: SourceInfo) => {
    const open = !collapsedSources.has(source.name);
    const tbls = tablesFor(source);
    return (
      <div className="tree-group" key={source.name}>
        <div
          className="tree-source"
          onClick={() => setCollapsedSources((s) => toggle(s, source.name))}
        >
          <span className={tbls.length ? "tree-ex" : "tree-ex tree-ex-leaf"}>
            {tbls.length ? (open ? "−" : "+") : ""}
          </span>
          <span>{source.name}</span>
        </div>
        {open &&
          tbls.map((t) =>
            tableNode(t, t.source === "memory" ? t.table : `${t.source}.${t.table}`, source),
          )}
      </div>
    );
  };

  return (
    <nav aria-label="Sources">
      {systems.map(([system, group]) => (
        <div className="tree-system" key={system}>
          <div className="tree-system-label">{system}</div>
          {group.map(sourceNode)}
        </div>
      ))}

      {uploads.length > 0 && (
        <div className="tree-system">
          <div className="tree-system-label">
            uploads <span className="type">session</span>
          </div>
          <div className="tree-group">{uploads.map((t) => tableNode(t, t.table))}</div>
        </div>
      )}

      <div className="tree-system">
        <div className="tree-system-label">
          local <span className="type">snapshots</span>
        </div>
        <div className="tree-group">
          {locals.length === 0 && <div className="hint tree-empty">empty</div>}
          {locals.map((t) => tableNode(t, `local.${t.table}`))}
        </div>
      </div>
    </nav>
  );
}
