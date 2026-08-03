import { useEffect, useRef, useState } from "react";
import embed from "vega-embed";
import { api, type EvalRun, type EvalSuite } from "../api";

const SUITE_TEMPLATE = `# Questions you actually ask, and what a correct answer must do.
# Run from the Run button above, or: datacharter eval --compare-guides
version: 1
cases:
  - question: "How many orders are there in total?"
    expect:
      - { type: sql_contains, value: "orders" }
      - { type: answer_matches, pattern: "\\\\d+" }
`;

/** Runs eval suites, shows the scorecard + guide-lift, edits suite YAML, and
 *  runs the contract's data tests. */
export default function EvalsView() {
  const [suites, setSuites] = useState<EvalSuite[]>([]);
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [running, setRunning] = useState(false);
  const [latest, setLatest] = useState<EvalRun | null>(null);
  const [compare, setCompare] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const trend = useRef<HTMLDivElement>(null);
  const [files, setFiles] = useState<{ name: string; content: string }[]>([]);
  const [editName, setEditName] = useState("");
  const [editContent, setEditContent] = useState("");
  const [editSaved, setEditSaved] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<
    { name: string; passed: boolean; failing_rows?: number; error?: string }[] | null
  >(null);

  const refresh = async () => {
    setSuites((await api.listEvals()).suites);
    setRuns((await api.evalHistory()).runs);
    const f = (await api.listEvalFiles().catch(() => ({ files: [] }))).files ?? [];
    setFiles(f);
    if (f.length > 0 && !f.some((x) => x.name === editName)) {
      setEditName(f[0].name);
      setEditContent(f[0].content);
    }
  };

  const pickSuite = (n: string) => {
    const f = files.find((x) => x.name === n);
    setEditName(n);
    setEditContent(f?.content ?? "");
    setEditSaved(false);
    setEditError(null);
  };

  const newSuite = () => {
    setEditName("");
    setEditContent(SUITE_TEMPLATE);
    setEditSaved(false);
    setEditError(null);
  };

  const saveSuite = async () => {
    setEditError(null);
    try {
      await api.saveEvalFile(editName, editContent);
      setEditSaved(true);
      setTimeout(() => setEditSaved(false), 1500);
      await refresh();
    } catch (e) {
      setEditError(e instanceof Error ? e.message : "Save failed.");
    }
  };

  const deleteSuite = async () => {
    if (!window.confirm(`Delete eval suite "${editName}"?`)) return;
    setEditError(null);
    try {
      await api.deleteEvalFile(editName);
      setEditName("");
      setEditContent("");
      await refresh();
    } catch (e) {
      setEditError(e instanceof Error ? e.message : "Delete failed.");
    }
  };

  const runTests = async () => {
    setTestResults(null);
    try {
      setTestResults((await api.runDataTests()).results);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Data tests failed to run.");
    }
  };
  useEffect(() => {
    void refresh();
  }, []);

  useEffect(() => {
    if (!trend.current || runs.length === 0) return;
    void embed(
      trend.current,
      {
        $schema: "https://vega.github.io/schema/vega-lite/v5.json",
        width: "container",
        data: { values: runs.map((r, i) => ({ run: i + 1, rate: r.overall.with_guides })) },
        mark: { type: "line", point: true },
        encoding: {
          x: { field: "run", type: "ordinal", title: "run" },
          y: {
            field: "rate",
            type: "quantitative",
            title: "pass rate",
            scale: { domain: [0, 1] },
          },
        },
      },
      { actions: false },
    ).catch(() => undefined);
  }, [runs]);

  const run = async () => {
    setRunning(true);
    setError(null);
    try {
      const res = await fetch("/api/evals/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ compare_guides: compare, samples: 1 }),
      });
      const reader = res.body?.getReader();
      if (!reader) return;
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const frames = buf.split("\n\n");
        buf = frames.pop() ?? "";
        for (const f of frames) {
          const line = f.split("\n").find((l) => l.startsWith("data:"));
          if (!line) continue;
          const ev = JSON.parse(line.slice(5));
          if (ev.overall) setLatest(ev as EvalRun);
        }
      }
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Eval run failed.");
    } finally {
      setRunning(false);
    }
  };

  const pct = (n: number) => `${Math.round(n * 100)}%`;

  return (
    <div className="evals-view">
      <header className="evals-header">
        <h2>Evals</h2>
        <label className="evals-compare">
          <input
            type="checkbox"
            checked={compare}
            onChange={(e) => setCompare(e.target.checked)}
          />{" "}
          compare guides
        </label>
        <button className="topbar-btn" onClick={run} disabled={running}>
          {running ? "Running…" : "Run"}
        </button>
      </header>

      {error && <div className="evals-error">{error}</div>}

      {suites.length === 0 && (
        <p className="evals-empty">
          No suites yet. Add <code>evals/*.yaml</code> to this workspace.
        </p>
      )}

      {suites.map((s) => (
        <section key={s.name} className="evals-suite">
          <h3>{s.name}</h3>
          <ul>
            {s.cases.map((c, i) => (
              <li key={i}>{c.question}</li>
            ))}
          </ul>
        </section>
      ))}

      <section className="evals-editor">
        <h3>Edit suites</h3>
        <div className="guides-tabs">
          {files.map((f) => (
            <button
              key={f.name}
              className={f.name === editName ? "guides-tab active" : "guides-tab"}
              onClick={() => pickSuite(f.name)}
            >
              {f.name}
            </button>
          ))}
          <button className="guides-tab" onClick={newSuite} aria-label="New eval suite">
            + New
          </button>
        </div>
        <input
          className="guides-name"
          value={editName}
          onChange={(e) => setEditName(e.target.value)}
          aria-label="suite name"
          placeholder="suite name (e.g. weekly-questions)"
        />
        <textarea
          className="guides-content"
          value={editContent}
          onChange={(e) => setEditContent(e.target.value)}
          rows={12}
          aria-label="suite yaml"
          placeholder="version: 1&#10;cases: …"
        />
        <div className="guides-actions">
          <button className="topbar-btn" onClick={saveSuite}>
            Save
          </button>
          {files.some((f) => f.name === editName) && (
            <button className="topbar-btn" onClick={deleteSuite} aria-label={`Delete suite ${editName}`}>
              Delete
            </button>
          )}
          {editSaved && <span className="guides-saved">Saved ✓</span>}
          {editError && <span className="guides-error">{editError}</span>}
        </div>
        <p className="evals-empty">
          Saving validates the YAML with the same checks <code>datacharter eval</code> uses —
          a suite that saves, runs.
        </p>
      </section>

      <section className="evals-datatests">
        <h3>
          Data tests{" "}
          <button className="topbar-btn" onClick={runTests} aria-label="Run data tests">
            Run tests
          </button>
        </h3>
        {testResults !== null && testResults.length === 0 && (
          <p className="evals-empty">
            No tests declared — add a <code>tests:</code> block to charter.yaml.
          </p>
        )}
        {testResults !== null && testResults.length > 0 && (
          <ul>
            {testResults.map((t) => (
              <li key={t.name}>
                {t.passed ? "✓" : "✗"} {t.name}
                {!t.passed && t.error && <span className="guides-error"> — {t.error}</span>}
                {!t.passed && !t.error && (
                  <span className="guides-error"> — {t.failing_rows} failing row(s)</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {latest && (
        <div className="evals-scorecard">
          <strong>{pct(latest.overall.with_guides)} passed</strong>
          {latest.overall.lift !== undefined && (
            <span className="evals-lift">
              {" · "}guides off {pct(latest.overall.without_guides ?? 0)} · lift{" "}
              {latest.overall.lift >= 0 ? "+" : ""}
              {pct(latest.overall.lift)}
            </span>
          )}
          <ul>
            {latest.cases.map((c, i) => (
              <li key={i}>
                {c.with_guides.passed ? "✓" : "✗"} {c.question}
                {c.with_guides.sqls.length > 0 && <pre>{c.with_guides.sqls.join("\n")}</pre>}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div ref={trend} className="evals-trend" />
    </div>
  );
}
