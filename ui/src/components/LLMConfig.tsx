import { useEffect, useState } from "react";
import { api, type AgentStatus } from "../api";

type LocalRuntime = { provider: string; base_url: string; models: string[] };

export default function LLMConfig({
  current,
  onDone,
  onCancel,
}: {
  current: AgentStatus | null;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [baseUrl, setBaseUrl] = useState(current?.base_url ?? "");
  const [model, setModel] = useState(current?.model ?? "");
  const [apiKey, setApiKey] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [msgKind, setMsgKind] = useState<"ok" | "pending" | "error">("pending");
  const [runtimes, setRuntimes] = useState<LocalRuntime[]>([]);

  useEffect(() => {
    api
      .localLLMs()
      .then((r) => setRuntimes(r.runtimes))
      .catch(() => undefined);
  }, []);

  const save = async () => {
    setMsg("Saving…");
    setMsgKind("pending");
    try {
      await api.configureLLM({
        base_url: baseUrl || undefined,
        model: model || undefined,
        api_key: apiKey || undefined,
      });
      onDone();
    } catch (e) {
      setMsg((e as Error).message);
      setMsgKind("error");
    }
  };

  // One click: a detected local model needs no key — connect straight away.
  const useLocal = async (rt: LocalRuntime, m: string) => {
    setBaseUrl(rt.base_url);
    setModel(m);
    setMsg(`Connecting ${m}…`);
    setMsgKind("pending");
    try {
      await api.configureLLM({ base_url: rt.base_url, model: m });
      onDone();
    } catch (e) {
      setMsg((e as Error).message);
      setMsgKind("error");
    }
  };

  return (
    <div className="llm-config">
      <h3>Connect an LLM</h3>
      {runtimes.length > 0 && (
        <div className="llm-local">
          <h4>Running on this machine</h4>
          {runtimes.map((rt) => (
            <div key={rt.provider} className="llm-local-runtime">
              <span className="llm-local-provider">{rt.provider}</span>
              <div className="llm-local-models">
                {rt.models.map((m) => (
                  <button
                    key={m}
                    className="guides-tab"
                    onClick={() => useLocal(rt, m)}
                    aria-label={`Use local model ${m}`}
                  >
                    {m}
                  </button>
                ))}
              </div>
            </div>
          ))}
          <p className="hint">One click — local models need no API key. Data stays on this machine.</p>
        </div>
      )}
      <div className="source-form">
        <label>
          Base URL
          <input
            value={baseUrl}
            placeholder="https://api.openai.com/v1"
            onChange={(e) => setBaseUrl(e.target.value)}
          />
        </label>
        <label>
          API key{current?.has_key ? " (blank = keep)" : ""}
          <input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
        </label>
        <label>
          Model
          <input
            value={model}
            placeholder="gpt-4o-mini"
            onChange={(e) => setModel(e.target.value)}
          />
        </label>
        <div className="source-form-actions">
          <button className="primary" onClick={save}>Save</button>
          <button onClick={onCancel}>Cancel</button>
        </div>
        {msg && <div className={`source-form-msg ${msgKind}`}>{msg}</div>}
      </div>
      <p className="hint">
        The API key is stored in your OS keyring, never on disk. Or set OPENAI_BASE_URL /
        OPENAI_API_KEY, or run <code>datacharter serve --local</code>.
      </p>
    </div>
  );
}
