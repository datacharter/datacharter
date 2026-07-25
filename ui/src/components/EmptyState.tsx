import { useRef, useState } from "react";

interface Props {
  onAddSource: () => void;
  onUpload: (file: File) => void;
  onLoadDemo: () => Promise<void>;
}

export default function EmptyState({ onAddSource, onUpload, onLoadDemo }: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadDemo = async () => {
    setLoading(true);
    setError(null);
    try {
      await onLoadDemo();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="empty-state">
      <h2>No data sources yet</h2>
      <p>Add a source to start exploring — it stays on your machine.</p>
      <div className="empty-actions">
        <button className="primary" onClick={onAddSource}>
          + Add a source
        </button>
        <button onClick={() => fileRef.current?.click()}>Drop a CSV</button>
        <button onClick={loadDemo} disabled={loading}>
          {loading ? "Loading…" : "Load the demo dataset"}
        </button>
      </div>
      {error && <div className="error-box">{error}</div>}
      <input
        ref={fileRef}
        type="file"
        accept=".csv,.parquet,.json"
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
