interface Props {
  top: Record<string, [unknown, number][]>;
  masked?: Set<string>;
}

/** Per-column top-value frequency bars shown under the SUMMARIZE table. */
export default function ProfileBars({ top, masked }: Props) {
  const cols = Object.keys(top);
  if (cols.length === 0) return null;
  return (
    <div className="profile-bars">
      {cols.map((col) => {
        const isMasked = masked?.has(col.toLowerCase());
        const rows = top[col];
        const max = Math.max(1, ...rows.map(([, c]) => c));
        return (
          <div key={col} className="profile-bar-col">
            <div className="profile-bar-name">{col}</div>
            {isMasked ? (
              <div className="profile-bar-hidden">••• hidden (PII)</div>
            ) : (
              rows.map(([value, count], i) => (
                <div key={i} className="profile-bar-row">
                  <span className="profile-bar-value" title={String(value)}>
                    {value === null ? "∅" : String(value)}
                  </span>
                  <span className="profile-bar-track">
                    <span
                      className="profile-bar-fill"
                      style={{ width: `${(count / max) * 100}%` }}
                    />
                  </span>
                  <span className="profile-bar-count">{count.toLocaleString()}</span>
                </div>
              ))
            )}
          </div>
        );
      })}
    </div>
  );
}
