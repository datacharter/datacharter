export interface Command {
  id: string;
  label: string;
  hint?: string;
  run: () => void;
}

/** Subsequence score: lower is better; null if `q` is not a subsequence of `label`. */
function score(label: string, q: string): number | null {
  const s = label.toLowerCase();
  let qi = 0;
  let pos = -1;
  let penalty = 0;
  for (let i = 0; i < s.length && qi < q.length; i++) {
    if (s[i] === q[qi]) {
      if (pos >= 0) penalty += i - pos - 1; // gap since the previous match
      if (i === 0 || " ._-/".includes(s[i - 1])) penalty -= 2; // reward word starts
      pos = i;
      qi++;
    }
  }
  return qi === q.length ? penalty : null;
}

export function fuzzyFilter(commands: Command[], query: string): Command[] {
  const q = query.trim().toLowerCase();
  if (!q) return commands;
  return commands
    .map((c) => ({ c, s: score(c.label, q) }))
    .filter((x): x is { c: Command; s: number } => x.s !== null)
    .sort((a, b) => a.s - b.s)
    .map((x) => x.c);
}
