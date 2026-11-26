"use client";
import { Cloud } from "lucide-react";
import { useState } from "react";
import { Button, ErrorBox } from "@/components/ui";

export default function Login() {
  const [key, setKey] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    const r = await fetch("/api/session", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key }) });
    setBusy(false);
    if (r.ok) window.location.href = "/";
    else setErr(((await r.json().catch(() => ({}))) as { detail?: string }).detail ?? "sign-in failed");
  }
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <div>
          <div className="flex items-center gap-2 text-lg font-semibold text-brand-700"><Cloud size={20} /> CloudGini</div>
          <p className="mt-1 text-sm text-slate-500">Optimize Cloud. Eliminate Waste. Secure Everything.</p>
        </div>
        <label className="block text-sm">
          <span className="text-slate-600">API key</span>
          <input type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 outline-none focus:border-brand-500" />
        </label>
        {err && <ErrorBox msg={err} />}
        <Button type="submit" disabled={busy || key.length < 8}>{busy ? "Checking…" : "Sign in"}</Button>
        <p className="text-xs text-slate-500">
          Local demo keys are printed once by <code>scripts/init-env.sh</code>. The key is kept in an httpOnly cookie and only sent to the CloudGini API.
        </p>
      </form>
    </div>
  );
}
