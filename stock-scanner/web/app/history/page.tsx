import Nav from "@/components/Nav";
import { SETUP_LABELS } from "@/lib/setup-labels";
import {
  HORIZONS,
  HORIZON_LABELS,
  byScoreBand,
  bySetupType,
  formatPercent,
  formatRate,
  overall,
  type Horizon,
} from "@/lib/stats";
import { historySetups, scoredHistory, type Setup } from "@/lib/supabase";

export const dynamic = "force-dynamic";

function StatTable({
  title,
  rows,
  note,
}: {
  title: string;
  rows: { label: string; sample: number; hitRate: number | null; avgReturn: number | null; medianReturn: number | null }[];
  note?: string;
}) {
  return (
    <div className="card">
      <h3>{title}</h3>
      {note && (
        <p className="subtle" style={{ margin: "2px 0 8px" }}>
          {note}
        </p>
      )}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Bucket</th>
              <th>n</th>
              <th>Hit rate</th>
              <th>Avg</th>
              <th>Median</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.label}>
                <td>
                  {SETUP_LABELS[r.label as keyof typeof SETUP_LABELS] ?? r.label}
                </td>
                <td className="subtle">{r.sample}</td>
                <td>{formatRate(r.hitRate)}</td>
                <td className={(r.avgReturn ?? 0) >= 0 ? "pos" : "neg"}>
                  {formatPercent(r.avgReturn)}
                </td>
                <td className={(r.medianReturn ?? 0) >= 0 ? "pos" : "neg"}>
                  {formatPercent(r.medianReturn)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function outcomeCell(value: number | null) {
  if (value === null) return <td className="subtle">—</td>;
  return <td className={value >= 0 ? "pos" : "neg"}>{formatPercent(value)}</td>;
}

export default async function HistoryPage({
  searchParams,
}: {
  searchParams: Promise<{ h?: string }>;
}) {
  const { h } = await searchParams;
  const horizon: Horizon = HORIZONS.includes(h as Horizon)
    ? (h as Horizon)
    : "fwd_10d";

  let rows: Setup[] = [];
  let stats: Setup[] = [];
  let error: string | null = null;
  try {
    [rows, stats] = await Promise.all([historySetups(), scoredHistory()]);
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
  }

  const all = overall(stats, horizon);

  return (
    <main className="shell">
      <div className="topbar">
        <div className="brand">
          Mind<span>Scan</span>
        </div>
        <div className="subtle">History &amp; outcomes</div>
      </div>

      <Nav />

      <div className="disclaimer">
        A &ldquo;hit&rdquo; just means the close was higher N trading days
        later. No targets, no stops, no position sizing — so this is a measure
        of whether the setups pointed the right way, not a strategy return.
      </div>

      {error && <div className="error">Could not load history: {error}</div>}

      <div className="filters">
        {HORIZONS.map((hz) => (
          <a
            key={hz}
            href={`/history?h=${hz}`}
            className={`chip ${hz === horizon ? "on" : ""}`}
          >
            {HORIZON_LABELS[hz]}
          </a>
        ))}
      </div>

      <div className="card">
        <h3>All setups · {HORIZON_LABELS[horizon]}</h3>
        <div className="stats" style={{ marginTop: 8 }}>
          <div className="stat">
            <div className="k">Sample</div>
            <div className="v">{all.sample}</div>
          </div>
          <div className="stat">
            <div className="k">Hit rate</div>
            <div className="v">{formatRate(all.hitRate)}</div>
          </div>
          <div className="stat">
            <div className="k">Avg return</div>
            <div className={`v ${(all.avgReturn ?? 0) >= 0 ? "pos" : "neg"}`}>
              {formatPercent(all.avgReturn)}
            </div>
          </div>
          <div className="stat">
            <div className="k">Median</div>
            <div className={`v ${(all.medianReturn ?? 0) >= 0 ? "pos" : "neg"}`}>
              {formatPercent(all.medianReturn)}
            </div>
          </div>
        </div>
      </div>

      <StatTable
        title={`By setup type · ${HORIZON_LABELS[horizon]}`}
        rows={bySetupType(stats, horizon)}
        note="Which setup types have actually worked."
      />

      <StatTable
        title={`By AI score band · ${HORIZON_LABELS[horizon]}`}
        rows={byScoreBand(stats, horizon)}
        note="Whether a higher AI score has meant a better outcome. If the bands don't separate, the score isn't adding information."
      />

      <h2 style={{ marginTop: 18 }}>Past setups</h2>
      {rows.length === 0 ? (
        <div className="empty">
          No setups have realized outcomes yet. The nightly job fills these in
          as the 5, 10, and 20-day horizons elapse.
        </div>
      ) : (
        <div className="card">
          <p className="subtle" style={{ margin: "0 0 8px" }}>
            Showing the {HORIZON_LABELS[horizon]} return — switch horizons above.
          </p>
          <div className="table-wrap">
            <table className="compact">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Ticker</th>
                  <th>Setup</th>
                  <th>Score</th>
                  <th>{HORIZON_LABELS[horizon]}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td className="subtle">{r.scan_date.slice(5)}</td>
                    <td style={{ fontWeight: 700 }}>{r.ticker}</td>
                    <td>
                      <span className={`badge ${r.setup_type}`}>
                        {SETUP_LABELS[r.setup_type] ?? r.setup_type}
                      </span>
                    </td>
                    <td>{r.ai_score ?? "—"}</td>
                    {outcomeCell(r[horizon])}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </main>
  );
}
