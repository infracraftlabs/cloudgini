import { NextRequest, NextResponse } from "next/server";
import { BACKEND_URL } from "@/lib/backend";

export async function POST(req: NextRequest) {
  const { key } = (await req.json().catch(() => ({}))) as { key?: string };
  if (!key || key.length < 8 || key.length > 256) {
    return NextResponse.json({ detail: "enter a valid API key" }, { status: 400 });
  }
  const r = await fetch(`${BACKEND_URL}/api/me`, { headers: { Authorization: `Bearer ${key}` }, cache: "no-store" });
  if (!r.ok) return NextResponse.json({ detail: "API key not accepted" }, { status: 401 });
  const res = NextResponse.json(await r.json());
  res.cookies.set("cg_key", key, {
    httpOnly: true, sameSite: "strict", secure: process.env.NODE_ENV === "production", path: "/", maxAge: 60 * 60 * 8,
  });
  return res;
}

export async function DELETE() {
  const res = NextResponse.json({ ok: true });
  res.cookies.delete("cg_key");
  return res;
}
