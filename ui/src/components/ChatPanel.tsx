import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";
import embed from "vega-embed";
import { api, type AgentStatus } from "../api";
import { captionForSpec } from "../lib/caption";
import { shouldAutoScroll } from "../lib/chatScroll";
import ClaudeCodeConnect from "./ClaudeCodeConnect";
import LLMConfig from "./LLMConfig";

interface ToolRun {
  tool: string;
  sql: string;
}

interface Msg {
  role: "user" | "assistant";
  text: string;
  tools: ToolRun[];
}

/** Streams agent answers over SSE; renders any ```vega-lite block inline. */
export default function ChatPanel({
  dark,
  onOpenSql,
}: {
  dark?: boolean;
  onOpenSql?: (sql: string) => void;
}) {
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [configuring, setConfiguring] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  const nearBottom = useRef(true);
  const claudeCode = status?.backend === "claude-code";
  const available = status ? status.available || claudeCode : null;
  const model = claudeCode ? "Claude Code (your subscription)" : (status?.model ?? "");

  const refresh = useCallback(() => {
    api.agentStatus().then(setStatus).catch(() => setStatus({ available: false } as AgentStatus));
  }, []);
  useEffect(refresh, [refresh]);

  useEffect(() => {
    if (nearBottom.current && scroller.current) {
      scroller.current.scrollTo(0, scroller.current.scrollHeight);
    }
  }, [messages]);

  const copyTranscript = useCallback(() => {
    const text = messages
      .map((m) => `${m.role === "user" ? "You" : "Agent"}: ${m.text}`)
      .join("\n\n");
    navigator.clipboard?.writeText(text).catch(() => {});
  }, [messages]);

  const ask = useCallback(async () => {
    const question = input.trim();
    if (!question || busy) return;
    setInput("");
    setBusy(true);
    setMessages((m) => [...m, { role: "user", text: question, tools: [] }]);
    setMessages((m) => [...m, { role: "assistant", text: "", tools: [] }]);

    const resp = await fetch("/api/agent/ask", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ question }),
    });
    if (!resp.body) {
      setBusy(false);
      return;
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let event = "";

    const patch = (fn: (m: Msg) => Msg) =>
      setMessages((all) => all.map((m, i) => (i === all.length - 1 ? fn(m) : m)));

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split("\n\n");
      buffer = chunks.pop() ?? "";
      for (const chunk of chunks) {
        for (const line of chunk.split("\n")) {
          if (line.startsWith("event: ")) event = line.slice(7);
          else if (line.startsWith("data: ")) {
            const data = JSON.parse(line.slice(6));
            if (event === "text") patch((m) => ({ ...m, text: m.text + data.text }));
            else if (event === "tool_call")
              patch((m) => ({ ...m, tools: [...m.tools, { tool: data.tool, sql: data.sql ?? "" }] }));
            else if (event === "error")
              patch((m) => ({ ...m, text: m.text + `\n\n⚠ ${data.detail}` }));
          }
        }
      }
    }
    setBusy(false);
  }, [input, busy]);

  if (configuring) {
    return (
      <div className="chat">
        <LLMConfig
          current={status}
          onDone={() => {
            setConfiguring(false);
            refresh();
          }}
          onCancel={() => setConfiguring(false)}
        />
      </div>
    );
  }

  if (available === false) {
    return (
      <div className="chat">
        <div className="chat-empty">
          <p>No agent connected.</p>
          <div className="connect-row">
            <button className="primary" onClick={() => setConfiguring(true)}>
              Connect an LLM
            </button>
            <ClaudeCodeConnect status={status} onDone={refresh} />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="chat">
      <div className="chat-head">
        <span className="hint">{model}</span>
        <button
          className="chat-config"
          title="Copy transcript"
          disabled={messages.length === 0}
          onClick={copyTranscript}
        >
          ⧉
        </button>
        <button
          className="chat-config"
          title="Clear chat"
          disabled={messages.length === 0 || busy}
          onClick={() => setMessages([])}
        >
          🗑
        </button>
        <button className="chat-config" title="Configure LLM" onClick={() => setConfiguring(true)}>
          ⚙
        </button>
      </div>
      <div
        className="chat-log"
        ref={scroller}
        onScroll={(e) => {
          const el = e.currentTarget;
          nearBottom.current = shouldAutoScroll(el.scrollTop, el.scrollHeight, el.clientHeight);
        }}
      >
        {messages.length === 0 && (
          <div className="chat-empty hint">
            Ask about your data{model ? ` — ${model}` : ""}. PII stays masked.
          </div>
        )}
        {messages.map((m, i) => (
          <Message key={i} msg={m} dark={dark} onOpenSql={onOpenSql} />
        ))}
        {busy &&
          messages[messages.length - 1]?.role === "assistant" &&
          !messages[messages.length - 1]?.text && (
            <div className="chat-typing" aria-live="polite">
              {claudeCode ? "Claude" : "The agent"} is typing<span className="dots">…</span>
            </div>
          )}
      </div>
      <div className="chat-input">
        <textarea
          value={input}
          placeholder="Ask your data…"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              ask();
            }
          }}
        />
        <button className="primary" onClick={ask} disabled={busy}>
          {busy ? "…" : "Ask"}
        </button>
      </div>
    </div>
  );
}

export function Message({
  msg,
  dark,
  onOpenSql,
}: {
  msg: Msg;
  dark?: boolean;
  onOpenSql?: (sql: string) => void;
}) {
  const { prose, spec } = splitVegaSpec(msg.text);
  const queries = msg.tools.filter((t) => t.sql);
  const others = msg.tools.filter((t) => !t.sql);
  return (
    <div className={`chat-msg ${msg.role}`}>
      {others.length > 0 && (
        <div className="chat-tools">{others.map((t) => `· ${t.tool}`).join(" ")}</div>
      )}
      {queries.map((t, i) => (
        <div className="chat-query" key={i}>
          <code className="chat-query-sql">{t.sql}</code>
          {onOpenSql && (
            <button className="chat-query-open" onClick={() => onOpenSql(t.sql)}>
              Open in editor
            </button>
          )}
        </div>
      ))}
      {prose && <div className="chat-prose">{renderProse(prose)}</div>}
      {spec && <VegaBlock spec={spec} dark={dark} />}
    </div>
  );
}

function VegaBlock({ spec, dark }: { spec: object; dark?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    embed(ref.current, spec as never, { actions: false, theme: dark ? "dark" : undefined }).catch(
      () => {},
    );
  }, [spec, dark]);
  const caption = captionForSpec(spec as never);
  return (
    <>
      {caption && <div className="chart-caption">{caption}</div>}
      <div className="chat-chart" ref={ref} />
    </>
  );
}

/** Render prose with ```fenced code``` blocks as <pre><code>; plain text otherwise. */
function renderProse(text: string): ReactNode[] {
  const parts: ReactNode[] = [];
  const fence = /```(?:\w*)\n?([\s\S]*?)```/g;
  let last = 0;
  let key = 0;
  let m: RegExpExecArray | null = fence.exec(text);
  while (m !== null) {
    if (m.index > last) parts.push(<span key={key++}>{text.slice(last, m.index)}</span>);
    parts.push(
      <pre className="chat-code" key={key++}>
        <code>{m[1].replace(/\n$/, "")}</code>
      </pre>,
    );
    last = m.index + m[0].length;
    m = fence.exec(text);
  }
  if (last < text.length) parts.push(<span key={key++}>{text.slice(last)}</span>);
  return parts;
}

function splitVegaSpec(text: string): { prose: string; spec: object | null } {
  const match = text.match(/```vega-lite\s*([\s\S]*?)```/);
  if (!match) return { prose: text, spec: null };
  let spec: object | null = null;
  try {
    spec = JSON.parse(match[1].trim());
  } catch {
    spec = null;
  }
  const prose = text.replace(match[0], "").trim();
  return { prose, spec };
}
