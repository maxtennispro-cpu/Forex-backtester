import { SETUP_LABELS, type Setup } from "@/lib/supabase";
import Sparkline from "./Sparkline";

function num(value: unknown, digits = 2): string {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toFixed(digits)
    : "—";
}

function scoreClass(score: number | null): string {
  if (score === null) return "low";
  if (score >= 75) return "high";
  if (score >= 50) return "mid";
  return "low";
}

export default function SetupCard({ setup }: { setup: Setup }) {
  const ind = setup.indicators ?? {};
  const rsi = ind.rsi as number | null;
  const relVol = ind.rel_volume as number | null;
  const fromHigh = ind.pct_from_52w_high as number | null;
  const atr = ind.atr as number | null;

  return (
    <article className="card">
      <div className="card-head">
        <div>
          <div className="ticker">{setup.ticker}</div>
          <div style={{ marginTop: 4 }}>
            <span className={`badge ${setup.setup_type}`}>
              {SETUP_LABELS[setup.setup_type] ?? setup.setup_type}
            </span>
          </div>
          <div className="meta" style={{ marginTop: 6 }}>
            Close ${num(setup.close)} · {setup.scan_date}
          </div>
        </div>
        <div className={`score ${scoreClass(setup.ai_score)}`}>
          <div className="value">{setup.ai_score ?? "—"}</div>
          <div className="label">AI score</div>
        </div>
      </div>

      {setup.ai_rationale && <p className="rationale">{setup.ai_rationale}</p>}

      {setup.ai_invalidation && (
        <div className="invalidation">
          <b>Invalidated:</b> {setup.ai_invalidation}
        </div>
      )}

      <div className="stats">
        <div className="stat">
          <div className="k">RSI</div>
          <div className="v">{num(rsi, 1)}</div>
        </div>
        <div className="stat">
          <div className="k">Rel vol</div>
          <div className="v">{relVol ? `${num(relVol, 1)}x` : "—"}</div>
        </div>
        <div className="stat">
          <div className="k">ATR</div>
          <div className="v">{num(atr)}</div>
        </div>
        <div className="stat">
          <div className="k">From 52w hi</div>
          <div className={`v ${fromHigh !== null && fromHigh < -0.15 ? "neg" : ""}`}>
            {fromHigh !== null && Number.isFinite(fromHigh)
              ? `${(fromHigh * 100).toFixed(1)}%`
              : "—"}
          </div>
        </div>
        <div className="stat">
          <div className="k">Trend</div>
          <div className="v">
            {ind.above_sma50 && ind.above_sma200
              ? "Up"
              : ind.above_sma200
                ? "Mixed"
                : "Down"}
          </div>
        </div>
      </div>

      <Sparkline closes={setup.closes} />
    </article>
  );
}
