import { useState } from "react";
import { api, type SourceFormData, type SourceInfo } from "../api";

const DB_FIELDS = ["host", "port", "database", "user", "schema"];
const TYPES = [
  "postgres", "mysql", "sqlite", "bigquery", "mssql",
  "snowflake", "csv", "parquet", "json",
];
const PATH_TYPES = ["csv", "parquet", "json", "sqlite"];  // use a path, no credentials

export default function SourceForm({
  editing,
  onDone,
  onCancel,
}: {
  editing?: SourceInfo;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [form, setForm] = useState<SourceFormData>({
    name: editing?.name ?? "",
    type: editing?.type ?? "postgres",
    connection: (editing?.connection as Record<string, string | number>) ?? {},
    path: editing?.path ?? undefined,
    tables: editing?.tables ?? [],
    pii: editing?.pii ?? {},
  });
  const [password, setPassword] = useState("");
  const [tested, setTested] = useState(!!editing);
  const [msg, setMsg] = useState<string | null>(null);

  const isFile = PATH_TYPES.includes(form.type);
  const payload = (): SourceFormData => ({ ...form, password: password || undefined });

  const test = async () => {
    setMsg("Testing…");
    try {
      await api.testSource(payload());
      setTested(true);
      setMsg("Connection OK");
    } catch (e) {
      setTested(false);
      setMsg((e as Error).message);
    }
  };

  const save = async () => {
    try {
      if (editing) await api.updateSource(form.name, payload());
      else await api.createSource(payload());
      onDone();
    } catch (e) {
      setMsg((e as Error).message);
    }
  };

  return (
    <div className="source-form">
      <label>
        Name
        <input
          value={form.name}
          disabled={!!editing}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
        />
      </label>
      <label>
        Type
        <select
          value={form.type}
          disabled={!!editing}
          onChange={(e) => setForm({ ...form, type: e.target.value, connection: {} })}
        >
          {TYPES.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
      </label>

      {isFile ? (
        <label>
          Path
          <input
            value={form.path ?? ""}
            onChange={(e) => setForm({ ...form, path: e.target.value })}
          />
        </label>
      ) : (
        DB_FIELDS.map((f) => (
          <label key={f}>
            {f}
            <input
              value={String(form.connection[f] ?? "")}
              onChange={(e) =>
                setForm({ ...form, connection: { ...form.connection, [f]: e.target.value } })
              }
            />
          </label>
        ))
      )}

      {!isFile && (
        <label>
          Password{editing ? " (blank = keep)" : ""}
          <input
            type="password"
            value={password}
            onChange={(e) => {
              setPassword(e.target.value);
              setTested(!!editing);
            }}
          />
        </label>
      )}

      <label>
        Tables (comma-separated)
        <input
          value={form.tables.join(", ")}
          onChange={(e) =>
            setForm({
              ...form,
              tables: e.target.value.split(",").map((s) => s.trim()).filter(Boolean),
            })
          }
        />
      </label>

      <div className="source-form-actions">
        <button onClick={test} className="secondary">Test connection</button>
        <button onClick={save} className="primary" disabled={!tested || !form.name}>Save</button>
        <button onClick={onCancel}>Cancel</button>
      </div>
      {msg && <div className="source-form-msg">{msg}</div>}
    </div>
  );
}
