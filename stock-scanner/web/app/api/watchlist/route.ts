import { NextResponse } from "next/server";
import {
  addToWatchlist,
  getWatchlist,
  removeFromWatchlist,
} from "@/lib/supabase";

/** Tickers are uppercased and dot-normalized to match the scanner (BRK.B -> BRK-B). */
function normalize(raw: unknown): string | null {
  if (typeof raw !== "string") return null;
  const ticker = raw.trim().toUpperCase().replace(/\./g, "-");
  return /^[A-Z][A-Z0-9-]{0,9}$/.test(ticker) ? ticker : null;
}

export async function GET() {
  try {
    return NextResponse.json({ tickers: await getWatchlist() });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}

export async function POST(req: Request) {
  const body = await req.json().catch(() => ({}));
  const ticker = normalize(body.ticker);
  if (!ticker) {
    return NextResponse.json(
      { error: "Enter a ticker like AAPL or BRK-B." },
      { status: 400 },
    );
  }
  try {
    await addToWatchlist(ticker);
    return NextResponse.json({ ok: true, ticker });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}

export async function DELETE(req: Request) {
  const ticker = normalize(new URL(req.url).searchParams.get("ticker"));
  if (!ticker) {
    return NextResponse.json({ error: "Invalid ticker." }, { status: 400 });
  }
  try {
    await removeFromWatchlist(ticker);
    return NextResponse.json({ ok: true });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
