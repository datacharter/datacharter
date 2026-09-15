/** Encode the current SQL into a `#sql=` fragment. Local-only; never auto-run. */
export function encodeQueryHash(sql: string): string {
  const bytes = new TextEncoder().encode(sql);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  const b64 = btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  return `#sql=${b64}`;
}

export function decodeQueryHash(hash: string): string | null {
  const raw = hash.startsWith("#") ? hash.slice(1) : hash;
  if (!raw.startsWith("sql=")) return null;
  const payload = raw.slice(4);
  if (!payload) return null;
  try {
    const pad = payload.length % 4 === 0 ? "" : "=".repeat(4 - (payload.length % 4));
    const b64 = payload.replace(/-/g, "+").replace(/_/g, "/") + pad;
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new TextDecoder().decode(bytes);
  } catch {
    return null;
  }
}
