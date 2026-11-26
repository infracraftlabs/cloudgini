import { NextRequest, NextResponse } from "next/server";
import { BACKEND_URL } from "@/lib/backend";

// Forwards /api/proxy/<path> to the backend's /api/<path>, adding the API key from the cookie.
async function forward(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  if (path.some((p) => p === ".." || p.includes("/"))) return NextResponse.json({ detail: "bad path" }, { status: 400 });
  const key = req.cookies.get("cg_key")?.value;
  if (!key) return NextResponse.json({ detail: "not signed in" }, { status: 401 });
  const url = `${BACKEND_URL}/api/${path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`;
  const init: RequestInit = {
    method: req.method,
    headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
    cache: "no-store",
  };
  if (req.method !== "GET") init.body = await req.text();
  const r = await fetch(url, init);
  return new NextResponse(await r.text(), { status: r.status, headers: { "Content-Type": "application/json" } });
}

export { forward as GET, forward as POST, forward as PUT, forward as PATCH };
