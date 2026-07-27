import { useEffect, useRef, useState } from "react";
import { api, type HistoryEntry } from "../api";
import { useFocusTrap } from "../lib/useFocusTrap";

function relTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const s = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

export default function HistoryPanel({
  onPick,
  onClose,
}: {
  onPick: (sql: string) => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useFocusTrap(ref, onClose);
  const [entries, setEntries] = useState<HistoryEntry[] | null>(null);

  useEffect(() => {
    api
      .history()
      .then((b) => setEntries(b.entries))
      .catch(() => setEntries([]));
  }, []);

  return (
    <div className="help-overlay" onClick={onClose}>
      <div
        className="history-panel"
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label="Query history"
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="help-head">
          <h2>Query history</h2>
          <button className="help-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        {entries === null && <p className="history-empty">Loading…</p>}
        {entries !== null && entries.length === 0 && (
          <p className="history-empty">No queries yet. Run one and it shows up here.</p>
        )}
        <ul className="history-list">
          {entries?.map((e, i) => (
            <li key={i}>
              <button
                className="history-item"
                onClick={() => {
                  onPick(e.sql);
                  onClose();
                }}
              >
                <code className="history-sql">{e.sql}</code>
                <span className="history-meta">
                  {relTime(e.ts)} · {e.row_count.toLocaleString()} row
                  {e.row_count === 1 ? "" : "s"}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
