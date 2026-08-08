/** Sequencing for the editor's two result producers — the debounced live
 *  preview and an explicit Run. Without this, a late preview response can land
 *  after Run and silently replace the full result with a 200-row capped one. */

export interface Epoch {
  /** Claim the latest token; any response holding an older token is stale. */
  next: () => number;
  isCurrent: (token: number) => boolean;
}

export function makeEpoch(): Epoch {
  let current = 0;
  return {
    next: () => ++current,
    isCurrent: (token: number) => token === current,
  };
}

const _body = (sql: string) => sql.replace(/--[^\n]*/g, "").trim();

/** Should the live preview fire? No when the SQL is empty/comment-only, a Run
 *  is in flight, or the SQL matches what Run last executed (modulo comments). */
export function shouldPreview(sql: string, lastRunSql: string | null, running: boolean): boolean {
  const body = _body(sql);
  return !!body && !running && body !== _body(lastRunSql ?? "");
}
