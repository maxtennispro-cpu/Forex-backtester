"use client";

import { useState } from "react";

export default function WatchlistEditor({ initial }: { initial: string[] }) {
  const [tickers, setTickers] = useState(initial);
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const res = await fetch("/api/watchlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ticker: input }),
    });
    const body = await res.json().catch(() => ({}));
    if (res.ok) {
      setTickers((prev) =>
        prev.includes(body.ticker) ? prev : [...prev, body.ticker].sort(),
      );
      setInput("");
    } else {
      setError(body.error ?? "Could not add that ticker.");
    }
    setBusy(false);
  }

  async function remove(ticker: string) {
    setError(null);
    const previous = tickers;
    setTickers((prev) => prev.filter((t) => t !== ticker));
    const res = await fetch(
      `/api/watchlist?ticker=${encodeURIComponent(ticker)}`,
      { method: "DELETE" },
    );
    if (!res.ok) {
      setTickers(previous); // put it back if the delete failed
      setError(`Could not remove ${ticker}.`);
    }
  }

  return (
    <>
      {error && <div className="error">{error}</div>}

      <div className="card">
        <form className="row" onSubmit={add}>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value.toUpperCase())}
            placeholder="Add a ticker (e.g. RKLB)"
            autoCapitalize="characters"
            autoCorrect="off"
            spellCheck={false}
            maxLength={10}
          />
          <button type="submit" disabled={busy || !input.trim()}>
            {busy ? "…" : "Add"}
          </button>
        </form>
      </div>

      <div className="card">
        <h3>
          Tracking {tickers.length} custom {tickers.length === 1 ? "name" : "names"}
        </h3>
        {tickers.length === 0 ? (
          <p className="subtle" style={{ margin: "8px 0 0" }}>
            Nothing yet. The index constituents are always scanned; add tickers
            here to include names outside them.
          </p>
        ) : (
          <div style={{ marginTop: 6 }}>
            {tickers.map((t) => (
              <div className="wl-row" key={t}>
                <span className="t">{t}</span>
                <button className="ghost" onClick={() => remove(t)}>
                  Remove
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
