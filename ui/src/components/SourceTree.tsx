import { type KeyboardEvent, useMemo, useState } from "react";
import type { SourceInfo, TableInfo } from "../api";

/** Make a non-button element behave as a keyboard-operable button. */
function pickableProps(onActivate: () => void) {
  return {
    role: "button" as const,
    tabIndex: 0,
    onClick: onActivate,
    onKeyDown: (e: KeyboardEvent) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        onActivate();
      }
    },
  };
}

interface Props {
  sources: SourceInfo[];
  tables: TableInfo[];
  onPick: (relation: string) => void;
  onRemove?: (kind: "snapshot" | "upload", name: string) => void;
  onSetAccess?: (a: { source: string; table?: string; column?: string; value: boolean }) => void;
  onRecheck?: (name: string) => Promise<{ changed: boolean; gone: number; new: number }>;
}

interface Remove {
  label: string;
  run: () => void;
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
export default function SourceTree({
  sources,
  tables,
  onPick,
  onRemove,
  onSetAccess,
  onRecheck,
}: Props) {
  // Per-snapshot recheck verdicts ("did this number change?"), shown inline.
  const [checks, setChecks] = useState<Record<string, string>>({});

  const recheck = async (name: string) => {
    if (!onRecheck) return;
    setChecks((c) => ({ ...c, [name]: "…" }));
    try {
      const r = await onRecheck(name);
      setChecks((c) => ({
        ...c,
        [name]: r.changed ? `CHANGED (−${r.gone} +${r.new})` : "unchanged ✓",
      }));
    } catch {
      setChecks((c) => ({ ...c, [name]: "recheck failed" }));
    }
  };
  const anyReal = (ts: TableInfo[]) =>
    ts.some((t) => Object.values(t.access ?? {}).some((a) => !a.masked));

  const accessToggle = (label: string, masked: boolean, onClick: () => void) => (
    <button
      type="button"
      className={masked ? "tree-access masked" : "tree-access"}
      aria-label={label}
      title={masked ? "Masked from agent — click to allow real values" : "Visible to agent — click to mask"}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
    >
      {masked ? "🙈" : "👁"}
    </button>
  );
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

  const tableNode = (
    t: TableInfo,
    relation: string,
    source?: SourceInfo,
    remove?: Remove,
    accessSource: string | undefined = source?.name,
  ) => {
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
          <span className="tree-table-name" {...pickableProps(() => onPick(relation))}>
            {t.table}
          </span>
          {source && piiFor(source, t.table) && <span className="pii">PII</span>}
          {accessSource &&
            onSetAccess &&
            t.access &&
            Object.keys(t.access).length > 0 &&
            accessToggle(`Toggle agent access for table ${t.table}`, !anyReal([t]), () =>
              onSetAccess({ source: accessSource, table: t.table, value: !anyReal([t]) }),
            )}
          {remove && (
            <button
              type="button"
              className="tree-remove"
              aria-label={remove.label}
              title={remove.label}
              onClick={(e) => {
                e.stopPropagation();
                remove.run();
              }}
            >
              ×
            </button>
          )}
        </div>
        {open && (
          <div className="tree-columns">
            {t.columns.map((c) => (
              <div className="tree-column" key={c}>
                <span className="tree-column-name" {...pickableProps(() => onPick(relation))}>
                  {c}
                </span>
                {t.access?.[c]?.pii && <span className="pii-dot" title="PII">•</span>}
                {accessSource &&
                  onSetAccess &&
                  t.access?.[c] &&
                  accessToggle(`Toggle agent access for ${c}`, t.access[c].masked, () =>
                    onSetAccess({
                      source: accessSource,
                      table: t.table,
                      column: c,
                      value: t.access![c].masked,
                    }),
                  )}
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
          {onSetAccess &&
            tbls.some((t) => t.access && Object.keys(t.access).length > 0) &&
            accessToggle(`Toggle agent access for source ${source.name}`, !anyReal(tbls), () =>
              onSetAccess({ source: source.name, value: !anyReal(tbls) }),
            )}
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
          <div className="tree-group">
            {uploads.map((t) =>
              tableNode(
                t,
                t.table,
                undefined,
                { label: `Remove ${t.table}`, run: () => onRemove?.("upload", t.table) },
                "local", // uploads persist their masking toggles via local_access
              ),
            )}
          </div>
        </div>
      )}

      <div className="tree-system">
        <div className="tree-system-label">
          local <span className="type">snapshots</span>
        </div>
        <div className="tree-group">
          {locals.length === 0 && <div className="hint tree-empty">empty</div>}
          {locals.map((t) => (
            <div key={`local.${t.table}`} className="tree-snapshot-row">
              {tableNode(
                t,
                `local.${t.table}`,
                undefined,
                { label: `Remove local.${t.table}`, run: () => onRemove?.("snapshot", t.table) },
                "local",
              )}
              {onRecheck && t.table !== "canaries" && (
                <div className="tree-recheck">
                  <button
                    type="button"
                    className="guides-tab"
                    aria-label={`Recheck local.${t.table}`}
                    title="Re-run this snapshot's query and diff it against the saved result"
                    onClick={() => recheck(t.table)}
                  >
                    recheck
                  </button>
                  {checks[t.table] && <span className="tree-recheck-note">{checks[t.table]}</span>}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </nav>
  );
}
