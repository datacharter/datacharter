export const ESTIMATE_WARN_ROWS = 1_000_000;

/** Format a cost pre-flight row estimate into a badge label + warn flag. */
export function formatEstimate(rows: number | null): { label: string; warn: boolean } {
  if (rows === null) return { label: "no estimate", warn: false };
  return { label: `~${rows.toLocaleString()} rows`, warn: rows > ESTIMATE_WARN_ROWS };
}
