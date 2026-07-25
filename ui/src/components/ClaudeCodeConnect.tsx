import { useState } from "react";

import { api, type AgentStatus } from "../api";

/** Connect the chat agent to the user's local Claude Code subscription (no API key).
 *  Shown only when the Claude Code CLI is available on the server host. */
export default function ClaudeCodeConnect({
  status,
  onDone,
}: {
  status: AgentStatus | null;
  onDone: () => void;
}) {
  const [msg, setMsg] = useState<string | null>(null);
  if (!status?.claude_code_available) return null;

  const connect = async () => {
    setMsg("Connecting… (verifying the tool sandbox)");
    try {
      await api.connectClaudeCode();
      onDone();
    } catch (e) {
      setMsg((e as Error).message);
    }
  };

  const switchToLlm = async () => {
    await api.setAgentBackend("llm");
    onDone();
  };

  const active = status.backend === "claude-code";
  return (
    <div className="cc-connect">
      {active ? (
        <>
          <div className="cc-status">✓ Agent: Claude Code (your subscription)</div>
          <button onClick={switchToLlm}>Switch to API LLM</button>
        </>
      ) : (
        <button className="primary" onClick={connect}>
          Connect Claude Code (your subscription)
        </button>
      )}
      {msg && <div className="source-form-msg">{msg}</div>}
      <p className="hint">
        Runs the chat on your local Claude Code — no API key. Data stays governed (read-only,
        PII-masked); connection is refused if the tool sandbox can't be verified.
      </p>
    </div>
  );
}
