import { useCallback, useEffect, useState } from "react";

interface Props {
  currentSql: () => string;
  onLoad: (sql: string) => void;
}

/** Toolbar controls for the file-based query library (queries/*.sql). */
export default function QueryFiles({ currentSql, onLoad }: Props) {
  const [names, setNames] = useState<string[]>([]);
  const [selected, setSelected] = useState("");

  const refresh = useCallback(() => {
    fetch("/api/queries")
      .then((r) => r.json())
      .then((b) => setNames(b.queries ?? []))
      .catch(() => {});
  }, []);

  useEffect(refresh, [refresh]);

  const load = async (name: string) => {
    setSelected(name);
    if (!name) return;
    const body = await (await fetch(`/api/queries/${name}`)).json();
    if (body.sql !== undefined) onLoad(body.sql);
  };

  const save = async () => {
    const name = window.prompt("Save as queries/<name>.sql", selected || "query");
    if (!name) return;
    const resp = await fetch("/api/queries", {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ name, sql: currentSql() }),
    });
    if (resp.ok) {
      setSelected(name);
      refresh();
    } else {
      window.alert((await resp.json()).error?.message ?? "Save failed");
    }
  };

  return (
    <>
      <select value={selected} onChange={(e) => load(e.target.value)} title="Open a saved query">
        <option value="">queries/…</option>
        {names.map((n) => (
          <option key={n} value={n}>
            {n}.sql
          </option>
        ))}
      </select>
      <button onClick={save} title="Save editor content to queries/<name>.sql">
        Save
      </button>
    </>
  );
}
