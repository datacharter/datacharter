import { useEffect, useState } from "react";
import { api, type AuditEntry, type AuditVerify } from "../api";

/** Session timeline of agent data access, with a live chain-verified badge. */
export default function AuditView() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [verify, setVerify] = useState<AuditVerify | null>(null);

  useEffect(() => {
    void (async () => {
      const [log, v] = await Promise.all([api.auditLog(), api.auditVerify()]);
      setEntries(log.entries);
      setVerify(v);
    })();
  }, []);

  const sessions = entries.filter((e) => e.type === "session");
  const accessesFor = (sid: string) =>
    entries.filter((e) => e.type === "access" && e.session === sid);
  const who = (s: AuditEntry) => s.client?.name ?? s.model ?? s.surface ?? "agent";

  return (
    <div className="audit-view">
      <header className="audit-header">
        <h2>Audit</h2>
        {verify && (
          <span className={verify.ok ? "audit-badge ok" : "audit-badge broken"}>
            {verify.ok ? `✓ chain verified · ${verify.entries} entries` : `⚠ ${verify.detail}`}
          </span>
        )}
      </header>
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
