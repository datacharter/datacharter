import { useCallback, useEffect, useState } from "react";
import { api } from "../api";

type TableState = {
  source: string;
  table: string;
  columns: string[];
  pii: Set<string>;
  rowFilter: string;
  aggregateOnly: boolean;
  noJoins: boolean;
  minGroup: string;
  noJoinsTo: string;
};

function relationKey(source: string, table: string): string {
  return source === table ? source : `${source}.${table}`;
}

function policiesFromSentences(sentences: string[]): Pick<
  TableState,
  "aggregateOnly" | "noJoins" | "minGroup" | "noJoinsTo"
> {
  let aggregateOnly = false;
  let noJoins = false;
  let minGroup = "";
  let noJoinsTo = "";
  for (const s of sentences) {
    const low = s.toLowerCase();
    if (low === "aggregates only" || low === "agents may only read aggregates") {
      aggregateOnly = true;
    } else if (low === "no joins") {
      noJoins = true;
    } else {
      const g = low.match(/^groups of at least (\d+)$/);
      if (g) minGroup = g[1];
      const j = s.match(/^(?:no joins to|never join to)\s+(.+)$/i);
      if (j) noJoinsTo = j[1];
    }
  }
  return { aggregateOnly, noJoins, minGroup, noJoinsTo };
}

function sentencesFrom(t: TableState): string[] {
  const out: string[] = [];
  if (t.aggregateOnly) out.push("aggregates only");
  if (t.minGroup && Number(t.minGroup) >= 2) out.push(`groups of at least ${t.minGroup}`);
  if (t.noJoins) out.push("no joins");
  if (t.noJoinsTo.trim()) out.push(`no joins to ${t.noJoinsTo.trim()}`);
  return out;
}

export default function CharterStudio({ onSaved }: { onSaved?: () => void }) {
  const [yaml, setYaml] = useState("");
  const [tables, setTables] = useState<TableState[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    const [charter, listing] = await Promise.all([api.charter(), api.tables()]);
    setYaml(charter.yaml);
    const sourceNames = new Set(charter.sources.map((s) => s.name));
    const next: TableState[] = listing.tables
      .filter((t) => sourceNames.has(t.source))
      .map((t) => {
        const src = charter.sources.find((s) => s.name === t.source);
        const piiCols = src?.pii?.[t.table] ?? src?.pii?.[t.source] ?? [];
        const key = relationKey(t.source, t.table);
        const sentences =
          charter.policies[key] ??
          charter.policies[t.table] ??
          charter.policies[t.source] ??
          [];
        return {
          source: t.source,
          table: t.table,
          columns: t.columns,
          pii: new Set(piiCols.map((c) => c.toLowerCase())),
          rowFilter: src?.row_filters?.[t.table] ?? src?.row_filters?.[t.source] ?? "",
          ...policiesFromSentences(sentences),
        };
      });
    setTables(next);
  }, []);

  useEffect(() => {
    load().catch((e) => setError((e as Error).message));
  }, [load]);

  const patch = (i: number, partial: Partial<TableState>) => {
    setTables((all) => all.map((t, idx) => (idx === i ? { ...t, ...partial } : t)));
  };

  const togglePii = (i: number, col: string) => {
    setTables((all) =>
      all.map((t, idx) => {
        if (idx !== i) return t;
        const pii = new Set(t.pii);
        const key = col.toLowerCase();
        if (pii.has(key)) pii.delete(key);
        else pii.add(key);
        return { ...t, pii };
      }),
    );
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.saveCharterStudio({
        pii: tables.map((t) => ({
          source: t.source,
          table: t.table,
          columns: t.columns.filter((c) => t.pii.has(c.toLowerCase())),
        })),
        row_filters: tables.map((t) => ({
          source: t.source,
          table: t.table,
          predicate: t.rowFilter,
        })),
        policies: tables.map((t) => ({
          relation: relationKey(t.source, t.table),
          sentences: sentencesFrom(t),
        })),
      });
      onSaved?.();
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="studio">
      <div className="studio-head">
        <h2>Charter Studio</h2>
        <button className="primary" onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save charter"}
        </button>
      </div>
      <p className="studio-lead">
        Toggle PII, row filters, and agent policies. charter.yaml is what gets saved.
      </p>
      {error && <div className="error-box">{error}</div>}
      <div className="studio-grid">
        <div className="studio-tables">
          {tables.length === 0 && (
            <p className="studio-empty">Add a source first, then edit its governance here.</p>
          )}
          {tables.map((t, i) => (
            <section key={`${t.source}.${t.table}`} className="studio-card">
              <h3>{t.source}.{t.table}</h3>
              <div className="studio-pii">
                <span className="studio-label">PII columns</span>
                {t.columns.map((col) => (
                  <label key={col}>
                    <input
                      type="checkbox"
                      checked={t.pii.has(col.toLowerCase())}
                      onChange={() => togglePii(i, col)}
                    />
                    {col}
                  </label>
                ))}
              </div>
              <label className="studio-field">
                Row filter
                <input
                  value={t.rowFilter}
                  onChange={(e) => patch(i, { rowFilter: e.target.value })}
                  placeholder="region = 'US'"
                />
              </label>
              <div className="studio-policies">
                <span className="studio-label">Agent policies</span>
                <label>
                  <input
                    type="checkbox"
                    checked={t.aggregateOnly}
                    onChange={(e) => patch(i, { aggregateOnly: e.target.checked })}
                  />
                  Aggregates only
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={t.noJoins}
                    onChange={(e) => patch(i, { noJoins: e.target.checked })}
                  />
                  No joins
                </label>
                <label className="studio-field">
                  Groups of at least
                  <input
                    type="number"
                    min={2}
                    value={t.minGroup}
                    onChange={(e) => patch(i, { minGroup: e.target.value })}
                    placeholder="off"
                  />
                </label>
                <label className="studio-field">
                  No joins to
                  <input
                    value={t.noJoinsTo}
                    onChange={(e) => patch(i, { noJoinsTo: e.target.value })}
                    placeholder="payments, invoices"
                  />
                </label>
              </div>
            </section>
          ))}
        </div>
        <pre className="studio-yaml" aria-label="charter.yaml">
          {yaml || "# charter.yaml"}
        </pre>
      </div>
    </div>
  );
}
