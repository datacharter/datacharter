import { type KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import { type Command, fuzzyFilter } from "../lib/commandPalette";
import { useFocusTrap } from "../lib/useFocusTrap";

/** ⌘K palette: fuzzy-filter tables/actions, run with Enter or click. */
export default function CommandPalette({
  commands,
  onClose,
}: {
  commands: Command[];
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  useFocusTrap(ref, onClose);
  const results = useMemo(() => fuzzyFilter(commands, query), [commands, query]);
  useEffect(() => setActive(0), [query]);

  const runAt = (i: number) => {
    const c = results[i];
    if (!c) return;
    onClose();
    c.run();
  };

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      runAt(active);
    }
  };

  return (
    <div className="cmdk-overlay" onClick={onClose}>
      <div
        className="cmdk"
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
      >
        <input
          className="cmdk-input"
          autoFocus
          placeholder="Type a command or table…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={onKeyDown}
        />
        <ul className="cmdk-list">
          {results.map((c, i) => (
            <li
              key={c.id}
              className={i === active ? "cmdk-item active" : "cmdk-item"}
              onMouseEnter={() => setActive(i)}
              onClick={() => runAt(i)}
            >
              <span>{c.label}</span>
              {c.hint && <span className="cmdk-hint">{c.hint}</span>}
            </li>
          ))}
          {results.length === 0 && <li className="cmdk-empty">No matches</li>}
        </ul>
      </div>
    </div>
  );
}
