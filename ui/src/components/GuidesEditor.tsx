import { useEffect, useState } from "react";
import { api, type GuidesPayload } from "../api";

type SuggestionItem = { kind: string; relation: string; text: string; count: number; total: number };

/** Author workspace guides (guides/*.md) and per-table context in the browser. */
export default function GuidesEditor() {
  const [payload, setPayload] = useState<GuidesPayload>({ guides: [], contexts: [] });
  const [name, setName] = useState("overview");
  const [content, setContent] = useState("");
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<SuggestionItem[]>([]);

  const load = async () => {
    const p = await api.listGuides();
    setPayload(p);
    const first = p.guides.find((x) => x.name === name) ?? p.guides[0];
    if (first) {
      setName(first.name);
      setContent(first.content);
    }
  };
  useEffect(() => {
    void load();
    void api
      .guideSuggestions()
      .then((r) => setSuggestions(r.suggestions))
      .catch(() => undefined);
  }, []);

  const addSuggestion = (s: SuggestionItem) => {
    setContent((c) => (c.endsWith("\n") || c === "" ? c : c + "\n") + `- ${s.text}\n`);
    setSuggestions((list) => list.filter((x) => x !== s));
    setSaved(false);
  };

  const pick = (n: string) => {
    const g = payload.guides.find((x) => x.name === n);
    setName(n);
    setContent(g?.content ?? "");
    setSaved(false);
  };

  const save = async () => {
    setError(null);
    try {
      await api.saveGuide({ name, content });
      setSaved(true);
      setTimeout(() => setSaved(false), 1500);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed.");
    }
  };

  const startNew = () => {
    setName("");
    setContent("");
    setSaved(false);
    setError(null);
  };

  const remove = async () => {
    if (!window.confirm(`Delete guide "${name}"? Agents stop receiving it immediately.`)) return;
    setError(null);
    try {
      await api.deleteGuide(name);
      setName("");
      setContent("");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed.");
    }
  };

  return (
    <div className="guides-editor">
      <header className="guides-header">
        <h2>Guides</h2>
        <p className="guides-sub">
          Context the agent reads before writing SQL — served to chat, Claude Code, and MCP clients.
        </p>
      </header>

      <div className="guides-tabs">
        {payload.guides.map((g) => (
          <button
            key={g.name}
            className={g.name === name ? "guides-tab active" : "guides-tab"}
            onClick={() => pick(g.name)}
          >
            {g.name}
          </button>
        ))}
        <button className="guides-tab" onClick={startNew} aria-label="New guide">
          + New
        </button>
      </div>

      <input
        className="guides-name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        aria-label="guide name"
        placeholder="guide name (e.g. analytics)"
      />
      <textarea
        className="guides-content"
        value={content}
        onChange={(e) => setContent(e.target.value)}
        rows={16}
        aria-label="guide content"
        placeholder="Explain your data the way you would to a colleague…"
      />
      <div className="guides-actions">
        <button className="topbar-btn" onClick={save}>
          Save
        </button>
        {payload.guides.some((g) => g.name === name) && (
          <button className="topbar-btn" onClick={remove} aria-label={`Delete guide ${name}`}>
            Delete
          </button>
        )}
        {saved && <span className="guides-saved">Saved ✓</span>}
        {error && <span className="guides-error">{error}</span>}
      </div>

      {suggestions.length > 0 && (
        <section className="guides-suggestions">
          <h3>Suggestions from your query history</h3>
          <p className="guides-sub">
            Habits mined from recent queries — add the ones that are true, then refine the wording.
          </p>
          <ul>
            {suggestions.map((s, i) => (
              <li key={i}>
                <span>{s.text}</span>
                <button className="guides-tab" onClick={() => addSuggestion(s)}>
                  Add
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {payload.contexts.length > 0 && (
        <section className="guides-contexts">
          <h3>Per-table context</h3>
          <ul>
            {payload.contexts.map((c, i) => (
              <li key={i}>
                <code>
                  {c.source}.{c.table}
                </code>{" "}
                — {c.context}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
