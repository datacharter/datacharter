import { useCallback, useEffect, useRef, useState } from "react";
import embed from "vega-embed";
import { api, type AgentStatus } from "../api";
import { captionForSpec } from "../lib/caption";
import LLMConfig from "./LLMConfig";

interface Msg {
  role: "user" | "assistant";
  text: string;
  tools: string[];
}

/** Streams agent answers over SSE; renders any ```vega-lite block inline. */
export default function ChatPanel({ dark }: { dark?: boolean }) {
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [configuring, setConfiguring] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  const available = status?.available ?? null;
  const model = status?.model ?? "";

  const refresh = useCallback(() => {
    api.agentStatus().then(setStatus).catch(() => setStatus({ available: false } as AgentStatus));
  }, []);
  useEffect(refresh, [refresh]);

  useEffect(() => {
    scroller.current?.scrollTo(0, scroller.current.scrollHeight);
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
              patch((m) => ({ ...m, tools: [...m.tools, data.tool] }));
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
          <p>No LLM connected.</p>
          <button className="primary" onClick={() => setConfiguring(true)}>
            Connect an LLM
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="chat">
      <div className="chat-head">
        <span className="hint">{model}</span>
        <button className="chat-config" title="Configure LLM" onClick={() => setConfiguring(true)}>
          ⚙
        </button>
      </div>
      <div className="chat-log" ref={scroller}>
        {messages.length === 0 && (
          <div className="chat-empty hint">
            Ask about your data{model ? ` — ${model}` : ""}. PII stays masked.
          </div>
        )}
        {messages.map((m, i) => (
          <Message key={i} msg={m} dark={dark} />
        ))}
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

function Message({ msg, dark }: { msg: Msg; dark?: boolean }) {
  const { prose, spec } = splitVegaSpec(msg.text);
  return (
    <div className={`chat-msg ${msg.role}`}>
      {msg.tools.length > 0 && (
        <div className="chat-tools">{msg.tools.map((t) => `· ${t}`).join(" ")}</div>
      )}
      {prose && <div className="chat-prose">{prose}</div>}
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
