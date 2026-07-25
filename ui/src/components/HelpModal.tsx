interface QA {
  q: string;
  a: string;
}

const ABOUT =
  "Contract-governed local data exploration, powered by DuckDB. Define your sources " +
  "as data contracts (charter.yaml), query them through DuckDB's federation engine with " +
  "real source pushdowns, and explore in this local web UI — charts, profiling, SQL editor — " +
  "and optionally ask questions in plain language. Your contract is the catalog; the " +
  "workspace is a directory you can commit.";

const FAQ: QA[] = [
  {
    q: "Does DataCharter collect any telemetry?",
    a: "No — zero telemetry, no phone-home. The server binds to 127.0.0.1 by default, reachable only from your machine unless you opt in with --host.",
  },
  {
    q: "Where does my data go? Is anything sent to a model?",
    a: "Query results stay local. The natural-language agent is optional; with no endpoint configured (or --local), nothing is sent anywhere. When the agent is on, PII columns — both those you declare under pii in charter.yaml and those DataCharter auto-detects — are masked (•••) before results reach the model, and you can adjust access per source, table, or column from the left panel.",
  },
  {
    q: "Can I use it fully offline?",
    a: "Yes. The app, engine, and UI run locally. DuckDB fetches a source extension the first time it is used (needs network once); after that, local files and bundled extensions need no connection. --local keeps the agent on your machine too.",
  },
  {
    q: "Is the engine read-only?",
    a: "Yes. A statement allowlist is enforced in the engine, so queries cannot modify your sources. The only write path is local.* DDL, used for snapshots into the workspace's encrypted local catalog.",
  },
  {
    q: "Which model can the agent use?",
    a: "Three options: your Claude Code subscription (click Connect Claude Code — no API key), any OpenAI-compatible /chat/completions endpoint (bring your own with OPENAI_BASE_URL + OPENAI_API_KEY), or fully local with `serve --local` (Ollama, qwen3:8b by default). There is no bundled or fine-tuned model.",
  },
  {
    q: "Is it free? Can my company use it?",
    a: "Yes — Apache-2.0, which permits commercial use.",
  },
  {
    q: "Do I need Docker, an account, or a database?",
    a: "No. It is one Python package running as a single process. No account, no application database — local state is a DuckDB file inside the workspace.",
  },
];

export default function HelpModal({ onClose }: { onClose: () => void }) {
  return (
    <div className="help-overlay" onClick={onClose}>
      <div className="help-modal" onClick={(e) => e.stopPropagation()}>
        <div className="help-head">
          <h2>DataCharter</h2>
          <button className="help-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        <p className="help-about">{ABOUT}</p>
        <h3>FAQ</h3>
        <dl className="help-faq">
          {FAQ.map((item) => (
            <div key={item.q}>
              <dt>{item.q}</dt>
              <dd>{item.a}</dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}
