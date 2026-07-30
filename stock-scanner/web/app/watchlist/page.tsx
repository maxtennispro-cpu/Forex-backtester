import Nav from "@/components/Nav";
import WatchlistEditor from "@/components/WatchlistEditor";
import { getWatchlist } from "@/lib/supabase";

export const dynamic = "force-dynamic";

export default async function WatchlistPage() {
  let tickers: string[] = [];
  let error: string | null = null;
  try {
    tickers = (await getWatchlist()).map((r) => r.ticker);
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
  }

  return (
    <main className="shell">
      <div className="topbar">
        <div className="brand">
          Mind<span>Scan</span>
        </div>
        <div className="subtle">Custom scan list</div>
      </div>

      <Nav />

      <div className="disclaimer">
        Anything you add here is scanned nightly alongside the S&amp;P 500 and
        Nasdaq 100 — so you can track names that aren&apos;t in either index.
      </div>

      {error && <div className="error">Could not load watchlist: {error}</div>}

      <WatchlistEditor initial={tickers} />
    </main>
  );
}
