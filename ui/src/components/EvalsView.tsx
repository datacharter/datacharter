import { useEffect, useRef, useState } from "react";
import embed from "vega-embed";
import { api, type EvalRun, type EvalSuite } from "../api";

/** Runs eval suites, shows the scorecard + guide-lift, and charts the trend. */
export default function EvalsView() {
  const [suites, setSuites] = useState<EvalSuite[]>([]);
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [running, setRunning] = useState(false);
  const [latest, setLatest] = useState<EvalRun | null>(null);
  const [compare, setCompare] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const trend = useRef<HTMLDivElement>(null);

  const refresh = async () => {
    setSuites((await api.listEvals()).suites);
    setRuns((await api.evalHistory()).runs);
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
