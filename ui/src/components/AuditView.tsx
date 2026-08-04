import { useEffect, useState } from "react";
import { api, type AuditEntry, type AuditVerify } from "../api";

/** Session timeline of agent data access, with a live chain-verified badge. */
export default function AuditView() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [verify, setVerify] = useState<AuditVerify | null>(null);
  const [canary, setCanary] = useState<{
    armed: boolean;
    mode: string | null;
    planted?: boolean | null;
  } | null>(null);

  useEffect(() => {
    void (async () => {
      const [log, v, c] = await Promise.all([
        api.auditLog(),
        api.auditVerify(),
        api.canaryStatus(),
      ]);
      setEntries(log.entries);
      setVerify(v);
      setCanary(c);
    })();
  }, []);

  const alarms = entries.filter((e) => e.type === ("alarm" as AuditEntry["type"]));

  const exportEvidence = async () => {
    // Same pack as `datacharter audit export`: entries + verification + charter + summary.
    const resp = await fetch("/api/audit/export", { method: "POST" });
    if (!resp.ok) return;
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "audit-evidence.zip";
    a.click();
    URL.revokeObjectURL(url);
  };

  const sessions = entries.filter((e) => e.type === "session");
  const accessesFor = (sid: string) =>
    entries.filter((e) => e.type === "access" && e.session === sid);
  const who = (s: AuditEntry) => s.client?.name ?? s.model ?? s.surface ?? "agent";

  return (
    <div className="audit-view">
      <header className="audit-header">
        <h2>Audit</h2>
        {verify && (
          <span
            className={
              !verify.ok
                ? "audit-badge broken"
                : verify.entries === 0
                  ? "audit-badge muted"
                  : "audit-badge ok"
            }
            title={verify.detail}
          >
            {!verify.ok
              ? `⚠ ${verify.detail}`
              : verify.entries === 0
                ? "no entries — nothing verified yet"
                : `✓ chain verified · ${verify.entries} entries`}
          </span>
        )}
        {entries.length > 0 && (
          <button
            className="topbar-btn"
            onClick={exportEvidence}
            title="Download a self-contained evidence pack: entries, verification result, the charter in force, and a summary."
          >
            Export evidence
          </button>
        )}
        {canary && (
          <span
            className={
              !canary.armed
                ? "audit-badge muted"
                : canary.planted === false
                  ? "audit-badge broken"
                  : "audit-badge ok"
            }
            title={
              !canary.armed
                ? "Canary tripwires plant synthetic honeytokens in a masked local table. If a token ever appears in agent output, masking provably failed. Enable with `canary: on` in charter.yaml."
                : canary.planted === false
                  ? "The charter says canary: on, but planting local.canaries FAILED — the honeytoken table is absent and only output scanning is active. Check the server log."
                  : `Canary tripwires armed (${canary.mode} mode): synthetic honeytokens are planted in local.canaries; if one ever appears in agent output, masking failed and an alarm lands here.`
            }
          >
            {!canary.armed
              ? "🪤 canary off"
              : canary.planted === false
                ? "🪤 canary DEGRADED — planting failed"
                : `🪤 canary armed (${canary.mode})`}
          </span>
        )}
      </header>

      {alarms.length > 0 && (
        <div className="audit-alarm">
          <strong>🚨 {alarms.length} canary alarm{alarms.length > 1 ? "s" : ""}</strong> — a
          masked value escaped to agent output. Investigate the entries below.
          <ul>
            {alarms.map((a) => (
              <li key={a.seq}>
                seq {a.seq} · {a.ts?.slice(0, 16)} · <code>{a.tool}</code>
                {a.sql && <pre className="audit-sql">{a.sql}</pre>}
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="audit-sub">
        Every agent data access, hash-chained and tamper-evident. Export evidence with{" "}
        <code>datacharter audit export</code>.
      </p>

      {sessions.length === 0 && (
        <p className="audit-empty">No agent access recorded yet. Ask the agent something.</p>
      )}

      {[...sessions].reverse().map((s) => {
        const acc = accessesFor(s.session);
        return (
          <section key={s.seq} className="audit-session">
            <div className="audit-session-head">
              <strong>{who(s)}</strong>
              <span className="audit-meta">
                [{s.surface}] · {s.user} · {s.ts?.slice(0, 16)}
                {acc.length > 0 && ` · ${acc.length} access${acc.length > 1 ? "es" : ""}`}
              </span>
            </div>
            {s.question && <div className="audit-question">“{s.question}”</div>}
            <ul className="audit-accesses">
              {acc.map((a) => (
                <li key={a.seq}>
                  <code className="audit-tool">{a.tool}</code>
                  {a.sql && <pre className="audit-sql">{a.sql}</pre>}
                  {a.relation && <code>{a.relation}</code>}
                  <span className="audit-meta">
                    {a.error
                      ? ` ${a.error}`
                      : ` ${a.row_count ?? "–"} rows` +
                        (a.masked_columns?.length
                          ? ` · masked: ${a.masked_columns.join(", ")}`
                          : "")}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
