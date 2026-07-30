"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export default function LoginPage() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const res = await fetch("/api/auth", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    if (res.ok) {
      router.replace("/");
      router.refresh();
    } else {
      const body = await res.json().catch(() => ({}));
      setError(body.error ?? "Incorrect password.");
      setBusy(false);
    }
  }

  return (
    <main className="login">
      <div className="card">
        <div className="brand">
          Mind<span>Scan</span>
        </div>
        <p className="subtle" style={{ marginTop: 6 }}>
          Personal stock scanner. Enter your password to continue.
        </p>
        {error && <div className="error" style={{ marginTop: 10 }}>{error}</div>}
        <form onSubmit={submit}>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password"
            autoFocus
            autoComplete="current-password"
          />
          <button type="submit" disabled={busy || !password}>
            {busy ? "Checking…" : "Unlock"}
          </button>
        </form>
      </div>
    </main>
  );
}
