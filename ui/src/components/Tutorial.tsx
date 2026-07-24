import { useState, type ReactNode } from "react";

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
          <code>Cmd/Ctrl+Enter</code> or <b>Run</b> for the full set. Here's one over
          the demo <code>store.orders</code> table.
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
  ];

  const [index, setIndex] = useState(0);
  const [done, setDone] = useState<boolean[]>(() => steps.map(() => false));
  const step = steps[index];
  const last = index === steps.length - 1;

  const close = () => {
    markSeen();
    onClose();
  };

  const act = () => {
    step.action?.run();
    setDone((d) => d.map((v, i) => (i === index ? true : v)));
    if (!last) setIndex(index + 1);
  };

  return (
    <aside className="tutorial" role="dialog" aria-label="Getting started">
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
