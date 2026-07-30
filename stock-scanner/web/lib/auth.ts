/**
 * Single-password gate.
 *
 * The cookie never contains the password — it holds a SHA-256 digest of
 * the password plus a fixed label. Both the login route and the Edge
 * middleware derive the same digest with Web Crypto, so verification works
 * in either runtime without a session store.
 */
export const SESSION_COOKIE = "scanner_session";

export async function sessionToken(password: string): Promise<string> {
  const data = new TextEncoder().encode(`stock-scanner:v1:${password}`);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/** Constant-time-ish comparison so a wrong cookie can't be timed out byte by byte. */
export function tokensMatch(a: string | undefined, b: string): boolean {
  if (!a || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

export async function expectedToken(): Promise<string | null> {
  const password = process.env.APP_PASSWORD;
  if (!password) return null;
  return sessionToken(password);
}
