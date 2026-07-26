import { useEffect, useMemo, useRef, useState } from "react";
import embed, { type Result as EmbedResult } from "vega-embed";
import type { QueryResult } from "../api";
import { applicableKinds, buildSpec, detectChart, type ChartConfig, type ChartKind } from "../lib/chartSpec";
import { captionForConfig } from "../lib/caption";
import { classifyColumns } from "../lib/columns";
import { withoutColumns } from "../lib/mask";

/** Auto-detected Vega-Lite chart with manual overrides; agent specs plug in later.
 *  With `maskColumns`, those columns are dropped entirely — a chart of ••• is
 *  meaningless, and dropping keeps raw PII out of Vega's embedded data (Agent view). */
export default function ChartPanel({
  result,
  dark,
  maskColumns,
}: {
  result: QueryResult;
  dark?: boolean;
  maskColumns?: Set<string>;
}) {
  const view = useMemo(
    () => (maskColumns ? withoutColumns(result, maskColumns) : result),
    [result, maskColumns],
  );
  const detected = useMemo(() => detectChart(view), [view]);
  const [config, setConfig] = useState<ChartConfig | null>(detected);
  const container = useRef<HTMLDivElement>(null);
  const embedded = useRef<EmbedResult | null>(null);

  useEffect(() => setConfig(detected), [detected]);

  useEffect(() => {
    if (!container.current || !config) return;
    let cancelled = false;
    embed(container.current, buildSpec(view, config), {
      actions: { export: true, source: false, compiled: false, editor: false },
      theme: dark ? "dark" : undefined,
    }).then((r) => {
      if (cancelled) r.view.finalize();
      else embedded.current = r;
    });
    return () => {
      cancelled = true;
      embedded.current?.view.finalize();
      embedded.current = null;
    };
  }, [view, config, dark]);

  if (!detected || !config) {
    return <div className="empty-state">No chartable columns in this result.</div>;
  }

  const classes = classifyColumns(view);
  const numericCols = view.columns.filter((c) => classes.get(c) === "numeric");
  const kinds = applicableKinds(view);

  return (
    <div className="chart-body">
      <div className="chart-controls">
        <label>
          type
          <select
            value={config.kind}
            onChange={(e) => setConfig({ ...config, kind: e.target.value as ChartKind })}
          >
            {kinds.map((k) => (
              <option key={k}>{k}</option>
            ))}
          </select>
        </label>
        <label>
          x
          <select
            value={config.x}
            onChange={(e) => setConfig({ ...config, x: e.target.value })}
          >
            {view.columns.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </label>
        <label>
          y
          <select
            value={config.y[0]}
            onChange={(e) => setConfig({ ...config, y: [e.target.value] })}
          >
            {numericCols.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </label>
      </div>
      <div ref={container} style={{ width: "100%" }} />
      <div className="chart-caption">
        {captionForConfig(config.kind, config.x, config.y[0] ?? "")}
      </div>
    </div>
  );
}
