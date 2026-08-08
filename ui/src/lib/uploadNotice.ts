/** The governance notice shown when a dropped file's columns were auto-masked.
 *  Returns null when nothing was flagged, so the caller shows no toast. */
export function uploadNotice(table: string, pii: string[]): string | null {
  if (!pii.length) return null;
  const cols = pii.join(", ");
  return (
    `PII detected in ${table}: ${cols} — auto-masked from agents (•••). ` +
    `Flip Agent view to see it; override in Sources.`
  );
}
