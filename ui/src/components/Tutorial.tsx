import { useRef, useState, type ReactNode } from "react";
import { useFocusTrap } from "../lib/useFocusTrap";

const SEEN_KEY = "datacharter.tutorial.v2.seen";

/** True once the tutorial has been seen; also true when storage is unavailable (never nag). */
export function hasSeenTutorial(): boolean {
  try {
    return localStorage.getItem(SEEN_KEY) === "1";
  } catch {
    return true;
  }
}

function markSeen(): void {
  try {
    localStorage.setItem(SEEN_KEY, "1");
  } catch {
    // Private mode / storage disabled — nothing to persist, and nothing breaks.
  }
}

export interface TutorialActions {
  loadAndRunExample: () => void;
  showChart: () => void;
  showProfile: () => void;
  /** Navigate to a top-level panel so a step can show the thing it describes. */
  showView: (view: "explorer" | "sources" | "evals" | "guides" | "audit") => void;
  toggleAgentView: () => void;
  /** Run a query with masked columns, then switch on Agent view. */
  runAgentExample: () => void;
}

interface Step {
  title: string;
  body: ReactNode;
  action?: { label: string; run: () => void };
}

interface Props {
  actions: TutorialActions;
  onClose: () => void;
}

/** First-run guided walkthrough of the core loop: non-modal, dismissible, shown once. */
export default function Tutorial({ actions, onClose }: Props) {
  const steps: Step[] = [
    {
      title: "Query — live",
      body: (
        <>
          The editor runs DuckDB SQL. Results <b>preview as you type</b>; press{" "}
          <code>Cmd/Ctrl+Enter</code> or <b>Run</b> for the full set. Here's an
          example over your data.
        </>
      ),
      action: { label: "Run the example", run: actions.loadAndRunExample },
    },
    {
      title: "Results show their work",
      body: (
        <>
          The grid shows your real values — it's your data, on your machine. Under it,{" "}
          <b>Reads …</b> lists which source columns the query touched. Flip{" "}
          <b>Agent view</b> to see exactly what the agent and MCP server get: PII
          columns masked, so the model never sees them.
        </>
      ),
    },
    {
      title: "Make a chart",
      body: (
        <>
          The Chart tab auto-detects a chart from your columns and captions it. Change
          the type or the x / y axes to explore.
        </>
      ),
      action: { label: "Open the chart", run: actions.showChart },
    },
    {
      title: "Profile a column",
      body: (
        <>
          Profile summarizes every column — nulls, distinct values, quartiles, and
          standard deviation — in a single pass.
        </>
      ),
      action: { label: "Run profile", run: actions.showProfile },
    },
    {
      title: "Ask your data",
      body: (
        <>
          Use <b>Ask your data</b> on the right to ask in plain English — the agent
          writes the SQL and can draw charts. Bring an OpenAI-compatible endpoint or
          run <code>datacharter serve --local</code>. The same governance applies: the
          agent is read-only and never sees raw PII.
        </>
      ),
    },
    {
      title: "The contract is the product",
      body: (
        <>
          Everything you just did is governed by <code>charter.yaml</code> — the file
          that says what your sources are, which columns are PII, and what an agent
          may touch. It lives in your repo: commit it, review it in a PR, clone it
          somewhere else and the whole governed workspace comes with it.
        </>
      ),
    },
    {
      title: "See what an agent sees",
      body: (
        <>
          This runs a query over PII columns and flips <b>Agent view</b>: the PII
          comes back as <code>•••</code> — that is literally the surface an AI agent
          gets, not a UI trick. Your own SQL is never restricted; the leash is only
          on agents. (Flip Agent view off to see the real values again.)
        </>
      ),
      action: { label: "Run a PII query", run: actions.runAgentExample },
    },
    {
      title: "Teach it your quirks",
      body: (
        <>
          Open <b>Guides</b>. Plain-language notes ("revenue is net of refunds",
          "exclude test accounts") are served to every agent — the built-in chat,
          Claude Desktop, Cursor. This demo ships one. Guides can even write
          themselves from your query history: <code>datacharter suggest</code>.
        </>
      ),
      action: { label: "Open Guides", run: () => actions.showView("guides") },
    },
    {
      title: "Rules in plain English",
      body: (
        <>
          This demo's charter says <code>aggregates only</code> and{" "}
          <code>groups of at least 2</code> for customers. So an agent asking for a
          list of emails is <b>refused</b>, and a GROUP BY only returns groups of 2 or
          more — the small ones are suppressed. Clean-room math, one YAML line.
        </>
      ),
    },
    {
      title: "Prove it happened",
      body: (
        <>
          Open <b>Audit</b>. Every agent query is recorded in a hash-chained log —
          who asked, what SQL ran, which columns were masked. This demo ships a real
          chain (including that policy refusal). Edit one entry and{" "}
          <code>datacharter audit verify</code> names the exact line that broke.
        </>
      ),
      action: { label: "Open Audit", run: () => actions.showView("audit") },
    },
    {
      title: "Measure it, don't trust it",
      body: (
        <>
          Open <b>Evals</b>. Write the questions you actually ask, and DataCharter
          scores how well the agent answers them — <code>--compare-guides</code> even
          tells you how much your written context improved accuracy. Governance you
          can prove, on your own data.
        </>
      ),
      action: { label: "Open Evals", run: () => actions.showView("evals") },
    },
  ];

  const [index, setIndex] = useState(0);
  const [done, setDone] = useState<boolean[]>(() => steps.map(() => false));
  const step = steps[index];
  const last = index === steps.length - 1;

  const ref = useRef<HTMLElement>(null);
  const close = () => {
    markSeen();
    onClose();
  };
  useFocusTrap(ref, close);

  const act = () => {
    step.action?.run();
    setDone((d) => d.map((v, i) => (i === index ? true : v)));
    if (!last) setIndex(index + 1);
  };

  return (
    <aside className="tutorial" role="dialog" aria-modal="true" aria-label="Getting started" ref={ref} tabIndex={-1}>
      <div className="tutorial-head">
        <span className="tutorial-title">Getting started</span>
        <button className="tutorial-close" onClick={close} aria-label="Close tutorial">
          ×
        </button>
      </div>
      <h3 className="tutorial-step-title">{step.title}</h3>
      <div className="tutorial-copy">{step.body}</div>
      {step.action && (
        <button className="primary tutorial-do" onClick={act}>
          {step.action.label}
        </button>
      )}
      <div className="tutorial-dots">
        {steps.map((s, i) => (
          <button
            key={s.title}
            className={`tutorial-dot${i === index ? " active" : ""}${done[i] ? " done" : ""}`}
            onClick={() => setIndex(i)}
            aria-label={`Step ${i + 1}: ${s.title}`}
          />
        ))}
      </div>
      <div className="tutorial-foot">
        <button onClick={() => setIndex(index - 1)} disabled={index === 0}>
          Back
        </button>
        <button className="tutorial-skip" onClick={close}>
          Skip tour
        </button>
        {last ? (
          <button className="primary" onClick={close}>
            Finish
          </button>
        ) : (
          <button onClick={() => setIndex(index + 1)}>Next</button>
        )}
      </div>
    </aside>
  );
}
