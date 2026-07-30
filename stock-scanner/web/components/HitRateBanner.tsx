import {
  formatPercent,
  formatRate,
  overall,
  type Horizon,
} from "@/lib/stats";
import { SETUP_LABELS } from "@/lib/setup-labels";
import type { Setup } from "@/lib/supabase";
import { bySetupType } from "@/lib/stats";

/**
 * Historical hit rate, shown above today's setups.
 *
 * This is the honesty check on everything below it: how often flagged
 * setups have actually closed higher N days later, from realized outcomes
 * only. If the sample is thin, it says so rather than implying an edge.
 */
export default function HitRateBanner({
  history,
  horizon = "fwd_10d",
}: {
  history: Setup[];
  horizon?: Horizon;
}) {
  const all = overall(history, horizon);
  const perType = bySetupType(history, horizon);

  if (all.sample === 0) {
    return (
      <div className="card">
        <h3>Historical hit rate</h3>
        <p className="subtle" style={{ margin: "6px 0 0" }}>
          No realized outcomes yet — the nightly job backfills what price did
          5, 10, and 20 days after each setup. Stats appear here once the first
          setups are old enough to measure.
        </p>
      </div>
    );
  }

  return (
    <div className="card">
      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <h3 style={{ margin: 0 }}>Historical hit rate · 10 days</h3>
        <span className="subtle" style={{ marginLeft: "auto" }}>
          n={all.sample}
        </span>
      </div>
      <div className="stats" style={{ marginTop: 10 }}>
        <div className="stat">
          <div className="k">All setups</div>
          <div className="v">{formatRate(all.hitRate)}</div>
        </div>
        <div className="stat">
          <div className="k">Avg return</div>
          <div className={`v ${(all.avgReturn ?? 0) >= 0 ? "pos" : "neg"}`}>
            {formatPercent(all.avgReturn)}
          </div>
        </div>
        {perType.map((b) => (
          <div className="stat" key={b.label}>
            <div className="k">
              {SETUP_LABELS[b.label as keyof typeof SETUP_LABELS] ?? b.label}
            </div>
            <div className="v">
              {formatRate(b.hitRate)}
              <span className="subtle" style={{ fontWeight: 400 }}>
                {" "}
                ({b.sample})
              </span>
            </div>
          </div>
        ))}
      </div>
      {all.sample < 40 && (
        <p className="subtle" style={{ margin: "10px 0 0" }}>
          Small sample — treat these percentages as provisional until the
          history builds up.
        </p>
      )}
    </div>
  );
}
