import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE, expectedToken, tokensMatch } from "@/lib/auth";

/**
 * Password gate for the whole app (Next 16 `proxy` convention — the former
 * `middleware.ts`). Everything except the login page and the auth endpoint
 * requires a valid session cookie.
 */
const PUBLIC_PATHS = ["/login", "/api/auth"];

export async function proxy(req: NextRequest) {
  const { pathname } = req.nextUrl;
  if (PUBLIC_PATHS.some((p) => pathname.startsWith(p))) {
    return NextResponse.next();
  }

  const expected = await expectedToken();
  if (!expected) {
    // No password configured — fail closed rather than serving data openly.
    return new NextResponse("APP_PASSWORD is not set on the server.", {
      status: 500,
    });
  }

  if (tokensMatch(req.cookies.get(SESSION_COOKIE)?.value, expected)) {
    return NextResponse.next();
  }

  if (pathname.startsWith("/api/")) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  const url = req.nextUrl.clone();
  url.pathname = "/login";
  url.search = "";
  return NextResponse.redirect(url);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
