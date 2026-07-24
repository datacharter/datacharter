import { useState } from "react";
import { api, type AgentStatus } from "../api";

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

  const save = async () => {
    setMsg("Saving…");
    try {
      await api.configureLLM({
        base_url: baseUrl || undefined,
        model: model || undefined,
        api_key: apiKey || undefined,
      });
      onDone();
    } catch (e) {
      setMsg((e as Error).message);
    }
  };

  return (
    <div className="llm-config">
      <h3>Connect an LLM</h3>
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
        {msg && <div className="source-form-msg">{msg}</div>}
      </div>
      <p className="hint">
        The API key is stored in your OS keyring, never on disk. Or set OPENAI_BASE_URL /
        OPENAI_API_KEY, or run <code>datacharter serve --local</code>.
      </p>
    </div>
  );
}
