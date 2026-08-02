import type { TopLevelSpec } from "vega-lite";
import type { QueryResult } from "../api";
import { classifyColumns, type ColumnClass } from "./columns";

export type ChartKind = "bar" | "line" | "area" | "scatter" | "pie";

export interface ChartConfig {
  kind: ChartKind;
  x: string;
  y: string[];
}

/** Heuristic default: date+numeric → line; categorical+numeric → bar; two numerics → scatter. */
export function detectChart(result: QueryResult): ChartConfig | null {
  const classes = classifyColumns(result);
  const of = (cls: ColumnClass) =>
    result.columns.filter((c) => classes.get(c) === cls);
  const dates = of("date");
  const nums = of("numeric");
  const cats = of("categorical");

  if (dates.length && nums.length) return { kind: "line", x: dates[0], y: nums.slice(0, 3) };
  if (cats.length && nums.length) return { kind: "bar", x: cats[0], y: nums.slice(0, 3) };
  if (nums.length >= 2) return { kind: "scatter", x: nums[0], y: [nums[1]] };
  return null;
}

export function applicableKinds(result: QueryResult): ChartKind[] {
  const classes = classifyColumns(result);
  const has = (cls: ColumnClass) => result.columns.some((c) => classes.get(c) === cls);
  const kinds: ChartKind[] = [];
  if (has("numeric")) {
    // Any second column can be an x axis — all-numeric results (ids, counts)
    // still bar/line/area fine; buildSpec types the axis per column class.
    if (result.columns.length >= 2) kinds.push("bar", "line", "area");
    if (has("categorical")) kinds.push("pie");
  }
  const numCount = result.columns.filter((c) => classes.get(c) === "numeric").length;
  if (numCount >= 2) kinds.push("scatter");
  return [...new Set(kinds)];
}

export function buildSpec(result: QueryResult, config: ChartConfig): TopLevelSpec {
  const data = result.rows.map((row) =>
    Object.fromEntries(result.columns.map((c, i) => [c, row[i]])),
  );
  const classes = classifyColumns(result);
  const xType = classes.get(config.x) === "date" ? "temporal" : classes.get(config.x) === "numeric" ? "quantitative" : "nominal";

  const base = { data: { values: data }, width: "container" as const, height: 320 };

  if (config.kind === "pie") {
    return {
      ...base,
      mark: { type: "arc", tooltip: true },
      encoding: {
        theta: { field: config.y[0], type: "quantitative" },
        color: { field: config.x, type: "nominal" },
      },
    };
  }
  if (config.kind === "scatter") {
    return {
      ...base,
      mark: { type: "point", tooltip: true },
      encoding: {
        x: { field: config.x, type: "quantitative" },
        y: { field: config.y[0], type: "quantitative" },
      },
    };
  }
  const mark = config.kind === "bar" ? "bar" : config.kind === "area" ? "area" : "line";
  if (config.y.length === 1) {
    return {
      ...base,
      mark: { type: mark, tooltip: true },
      encoding: {
        x: { field: config.x, type: xType },
        y: { field: config.y[0], type: "quantitative" },
      },
    };
  }
  return {
    ...base,
    transform: [{ fold: config.y, as: ["series", "value"] }],
    mark: { type: mark, tooltip: true },
    encoding: {
      x: { field: config.x, type: xType },
      y: { field: "value", type: "quantitative" },
      color: { field: "series", type: "nominal" },
    },
  };
}
