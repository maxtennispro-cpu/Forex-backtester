import { Suspense } from "react";
import Filters from "@/components/Filters";
import HitRateBanner from "@/components/HitRateBanner";
import Nav from "@/components/Nav";
import SetupCard from "@/components/SetupCard";
import { latestScanDate, scoredHistory, setupsForDate } from "@/lib/supabase";

export const dynamic = "force-dynamic";

export default async function TodayPage({
  searchParams,
}: {
  searchParams: Promise<{ type?: string; min?: string }>;
}) {
  const { type, min } = await searchParams;
  const minScore = Number(min ?? 0) || 0;

  let scanDate: string | null = null;
  let setups: Awaited<ReturnType<typeof setupsForDate>> = [];
  let history: Awaited<ReturnType<typeof scoredHistory>> = [];
  let error: string | null = null;

  try {
    scanDate = await latestScanDate();
    [setups, history] = await Promise.all([
      scanDate ? setupsForDate(scanDate) : Promise.resolve([]),
      scoredHistory(),
    ]);
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
  }

  const visible = setups.filter(
    (s) =>
      (!type || s.setup_type === type) &&
      (minScore === 0 || (s.ai_score ?? 0) >= minScore),
  );

  return (
    <main className="shell">
      <div className="topbar">
        <div className="brand">
          Mind<span>Scan</span>
        </div>
        <div className="subtle">
          {scanDate ? `Scan of ${scanDate}` : "No scans yet"}
        </div>
      </div>

      <Nav />

      <div className="disclaimer">
        These are <b>setups to review</b>, not recommendations. Nothing here is
        advice to buy or sell anything, and AI scores are opinions about chart
        structure — not forecasts. Check the hit-rate stats below before
        trusting any of it.
      </div>

      {error && <div className="error">Could not load setups: {error}</div>}

      <HitRateBanner history={history} />

      <h1 style={{ marginTop: 18 }}>
        Today&apos;s setups{" "}
        <span className="subtle" style={{ fontSize: 14, fontWeight: 400 }}>
          ({visible.length}
          {visible.length !== setups.length ? ` of ${setups.length}` : ""})
        </span>
      </h1>

      <Suspense fallback={null}>
        <Filters />
      </Suspense>

      {visible.length === 0 ? (
        <div className="empty">
          {setups.length === 0
            ? "No setups flagged in the latest scan. Quiet days are normal — the scanner only reports when its conditions are met."
            : "No setups match these filters."}
        </div>
      ) : (
        visible.map((s) => <SetupCard key={s.id} setup={s} />)
      )}
    </main>
  );
}
