/**
 * Server-side Supabase (PostgREST) access.
 *
 * The service-role key is read from a non-public env var and used only in
 * server components and route handlers, so it never reaches the browser.
 */
import "server-only";
import { SETUP_LABELS, type SetupType } from "./setup-labels";

export { SETUP_LABELS };
export type { SetupType };

export interface Setup {
  id: number;
  scan_date: string;
  ticker: string;
  setup_type: SetupType;
  close: number;
  volume: number;
  indicators: Record<string, number | boolean | null>;
  closes: number[];
  ai_score: number | null;
  ai_rationale: string | null;
  ai_invalidation: string | null;
  fwd_5d: number | null;
  fwd_10d: number | null;
  fwd_20d: number | null;
}

function config() {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_KEY;
  if (!url || !key) {
    throw new Error("SUPABASE_URL and SUPABASE_KEY must be set");
  }
  return {
    base: `${url.replace(/\/$/, "")}/rest/v1`,
    headers: {
      apikey: key,
      Authorization: `Bearer ${key}`,
      "Content-Type": "application/json",
    },
  };
}

async function rest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const { base, headers } = config();
  const res = await fetch(`${base}/${path}`, {
    ...init,
    headers: { ...headers, ...(init.headers ?? {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Supabase ${res.status}: ${await res.text()}`);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

/** The most recent date that has any setups, so the app follows the last scan. */
export async function latestScanDate(): Promise<string | null> {
  const rows = await rest<{ scan_date: string }[]>(
    "setups?select=scan_date&order=scan_date.desc&limit=1",
  );
  return rows[0]?.scan_date ?? null;
}

export async function setupsForDate(date: string): Promise<Setup[]> {
  return rest<Setup[]>(
    `setups?scan_date=eq.${date}` +
      "&order=ai_score.desc.nullslast,ticker.asc&limit=500",
  );
}

/** Setups old enough to have outcomes, newest first — the history view. */
export async function historySetups(limit = 400): Promise<Setup[]> {
  return rest<Setup[]>(
    "setups?fwd_5d=not.is.null" +
      `&order=scan_date.desc,ai_score.desc.nullslast&limit=${limit}`,
  );
}

/** Every setup with at least one realized outcome — the hit-rate sample. */
export async function scoredHistory(): Promise<Setup[]> {
  return rest<Setup[]>(
    "setups?fwd_5d=not.is.null" +
      "&select=setup_type,ai_score,fwd_5d,fwd_10d,fwd_20d&limit=5000",
  );
}

export async function getWatchlist(): Promise<{ ticker: string }[]> {
  return rest<{ ticker: string }[]>("watchlist?select=ticker&order=ticker.asc");
}

export async function addToWatchlist(ticker: string): Promise<void> {
  await rest("watchlist?on_conflict=ticker", {
    method: "POST",
    headers: { Prefer: "resolution=ignore-duplicates,return=minimal" },
    body: JSON.stringify({ ticker }),
  });
}

export async function removeFromWatchlist(ticker: string): Promise<void> {
  await rest(`watchlist?ticker=eq.${encodeURIComponent(ticker)}`, {
    method: "DELETE",
    headers: { Prefer: "return=minimal" },
  });
}
