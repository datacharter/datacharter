// Deterministic one-line captions for charts — a plain-language narration of
// what a chart shows, derived from its config or Vega-Lite spec (no LLM needed).

interface VLSpec {
  mark?: string | { type?: string };
  encoding?: { x?: { field?: string }; y?: { field?: string } };
}

export function captionForConfig(kind: string, x: string, y: string): string {
  return `${kind} of ${y} by ${x}`;
}

export function captionForSpec(spec: VLSpec): string | null {
  const mark = typeof spec.mark === "string" ? spec.mark : spec.mark?.type;
  const x = spec.encoding?.x?.field;
  const y = spec.encoding?.y?.field;
  if (!mark) return null;
  if (x && y) return `${mark} of ${y} by ${x}`;
  return `${mark} chart`;
}
