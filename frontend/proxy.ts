import { NextRequest, NextResponse } from "next/server";

// Every page needs a session cookie; the API key itself stays in an httpOnly cookie
// and is only ever sent server-side to the backend by app/api/proxy.
export function proxy(req: NextRequest) {
  const { pathname } = req.nextUrl;
  if (pathname.startsWith("/login") || pathname.startsWith("/api/session") || pathname.startsWith("/_next")) {
    return NextResponse.next();
  }
  if (!req.cookies.get("cg_key")) {
    if (pathname.startsWith("/api/")) return NextResponse.json({ detail: "not signed in" }, { status: 401 });
    return NextResponse.redirect(new URL("/login", req.url));
  }
  return NextResponse.next();
}

export const config = { matcher: ["/((?!favicon.ico|icon.svg).*)"] };
