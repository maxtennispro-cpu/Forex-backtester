/**
 * Hit-rate statistics over realized outcomes.
 *
 * A "hit" is simply a positive forward return at the horizon — no target,
 * no stop, no position sizing. These numbers describe what the flagged
 * setups did historically; they are not a strategy result and not a
 * prediction.
 */
import type { Setup, SetupType } from "./supabase";

export type Horizon = "fwd_5d" | "fwd_10d" | "fwd_20d";
export const HORIZONS: Horizon[] = ["fwd_5d", "fwd_10d", "fwd_20d"];
export const HORIZON_LABELS: Record<Horizon, string> = {
  fwd_5d: "5 days",
  fwd_10d: "10 days",
  fwd_20d: "20 days",
};

export interface Bucket {
  label: string;
  sample: number;
  hitRate: number | null; // fraction 0-1 of positive outcomes
  avgReturn: number | null; // mean percent change
  medianReturn: number | null;
}

function summarize(label: string, values: number[]): Bucket {
  if (values.length === 0) {
    return { label, sample: 0, hitRate: null, avgReturn: null, medianReturn: null };
  }
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return {
    label,
    sample: values.length,
    hitRate: values.filter((v) => v > 0).length / values.length,
    avgReturn: values.reduce((a, b) => a + b, 0) / values.length,
    medianReturn:
      sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2,
  };
}

function pick(rows: Setup[], horizon: Horizon): number[] {
  return rows
    .map((r) => r[horizon])
    .filter((v): v is number => typeof v === "number");
}

/** One row per setup type, for a given horizon. */
export function bySetupType(rows: Setup[], horizon: Horizon): Bucket[] {
  const types = [...new Set(rows.map((r) => r.setup_type))].sort();
  return types.map((t) =>
    summarize(t, pick(rows.filter((r) => r.setup_type === t), horizon)),
  );
}

/** Score bands, to show whether the AI score actually separates outcomes. */
export function byScoreBand(rows: Setup[], horizon: Horizon): Bucket[] {
  const bands: [string, (s: number) => boolean][] = [
    ["80-100", (s) => s >= 80],
    ["60-79", (s) => s >= 60 && s < 80],
    ["40-59", (s) => s >= 40 && s < 60],
    ["1-39", (s) => s < 40],
  ];
  return bands.map(([label, test]) =>
    summarize(
      label,
      pick(
        rows.filter((r) => typeof r.ai_score === "number" && test(r.ai_score)),
        horizon,
      ),
    ),
  );
}

export function overall(rows: Setup[], horizon: Horizon): Bucket {
  return summarize("All setups", pick(rows, horizon));
}

export function formatPercent(value: number | null, digits = 1): string {
  if (value === null || Number.isNaN(value)) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

export function formatRate(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(0)}%`;
}
