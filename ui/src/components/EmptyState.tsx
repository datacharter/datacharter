import { useRef, useState } from "react";

interface Props {
  onAddSource: () => void;
  onUpload: (file: File) => void;
  onLoadDemo: () => Promise<void>;
  onCharterFiles?: () => Promise<void>;
}

export default function EmptyState({ onAddSource, onUpload, onLoadDemo, onCharterFiles }: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [loading, setLoading] = useState<"demo" | "charter" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async (kind: "demo" | "charter", fn: () => Promise<void>) => {
    setLoading(kind);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(null);
    }
  };

  return (
    <div className="empty-state">
      <h2>Drop a file, or charter this folder</h2>
      <p>It stays on your machine. SQL is a tab once there is data to see.</p>
      <div className="empty-actions">
        <button className="primary" onClick={() => fileRef.current?.click()}>
          Drop a CSV
        </button>
        {onCharterFiles && (
          <button
            onClick={() => run("charter", onCharterFiles)}
            disabled={loading !== null}
          >
            {loading === "charter" ? "Scanning…" : "Charter files in this folder"}
          </button>
        )}
        <button onClick={onAddSource}>Add a source</button>
        <button onClick={() => run("demo", onLoadDemo)} disabled={loading !== null}>
          {loading === "demo" ? "Loading…" : "Load the demo dataset"}
        </button>
      </div>
      {error && <div className="error-box">{error}</div>}
      <input
        ref={fileRef}
        type="file"
        accept=".csv,.parquet,.json,.xlsx"
        style={{ display: "none" }}
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onUpload(f);
          e.target.value = "";
        }}
      />
    </div>
  );
}
