import { useEffect, useState } from "react";
import { api, type SourceInfo } from "../api";
import SourceForm from "./SourceForm";

export default function SourcesView({ onChange }: { onChange: () => void }) {
  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [editing, setEditing] = useState<SourceInfo | "new" | null>(null);

  const load = () => api.sources().then((r) => setSources(r.sources)).catch(() => {});
  useEffect(() => {
    load();
  }, []);

  const done = () => {
    setEditing(null);
    load();
    onChange();
  };

  if (editing) {
    return (
      <div className="sources-view">
        <h2>{editing === "new" ? "Add source" : `Edit ${editing.name}`}</h2>
        <SourceForm
          editing={editing === "new" ? undefined : editing}
          onDone={done}
          onCancel={() => setEditing(null)}
        />
      </div>
    );
  }

  const remove = async (name: string) => {
    if (!confirm(`Delete source "${name}"? Its stored credential is removed too.`)) return;
    await api.deleteSource(name);
    load();
    onChange();
  };

  return (
    <div className="sources-view">
      <div className="sources-head">
        <h2>Sources</h2>
        <button className="primary" onClick={() => setEditing("new")}>+ Add source</button>
      </div>
      <table className="sources-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Type</th>
            <th>Tables</th>
            <th>Credential</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {sources.map((s) => (
            <tr key={s.name}>
              <td>{s.name}</td>
              <td>{s.type}</td>
              <td>{s.tables.length || "—"}</td>
              <td>{s.has_credential ? "✓" : "—"}</td>
              <td>
                <button onClick={() => setEditing(s)}>Edit</button>
                <button onClick={() => remove(s.name)}>Delete</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
