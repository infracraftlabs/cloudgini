"use client";
import clsx from "clsx";
import { Bot, Cloud, Gauge, History, ListChecks, Settings, ShieldCheck, Trash2, Wallet, Wrench, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { createContext, ReactNode, useContext, useState } from "react";
import { api, useApi } from "@/lib/api";
import type { Me } from "@/lib/types";
import { Badge, Button } from "./ui";

const NAV = [
  { href: "/", label: "Overview", icon: Gauge },
  { href: "/cost", label: "Cost Optimization", icon: Wallet },
  { href: "/cleanup", label: "Resource Cleanup", icon: Trash2 },
  { href: "/security", label: "Security", icon: ShieldCheck },
  { href: "/recommendations", label: "Recommendations", icon: ListChecks },
  { href: "/remediation", label: "Remediation Center", icon: Wrench },
  { href: "/accounts", label: "Cloud Accounts", icon: Cloud },
  { href: "/audit", label: "Audit History", icon: History },
  { href: "/settings", label: "Settings", icon: Settings },
];

const MeContext = createContext<Me | null>(null);
export const useMe = () => useContext(MeContext);
export const can = (me: Me | null, perm: string) => !!me?.permissions.includes(perm);
export const needs = (perm: string) => `Needs a role with the '${perm}' permission`;

const AssistantContext = createContext<(recId?: string) => void>(() => {});
export const useAssistant = () => useContext(AssistantContext);

export function Shell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const { data: me } = useApi<Me>(path === "/login" ? null : "/me");
  const [assistant, setAssistant] = useState<{ open: boolean; recId?: string }>({ open: false });
  if (path === "/login") return <>{children}</>;
  return (
    <MeContext.Provider value={me}>
      <AssistantContext.Provider value={(recId) => setAssistant({ open: true, recId })}>
        <div className="flex min-h-screen">
          <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-slate-200 bg-white md:flex">
            <div className="px-5 py-5">
              <div className="flex items-center gap-2 text-lg font-semibold text-brand-700"><Cloud size={20} /> CloudGini</div>
              <div className="mt-0.5 text-[11px] leading-tight text-slate-500">Optimize Cloud. Eliminate Waste. Secure Everything.</div>
            </div>
            <nav className="flex-1 space-y-0.5 px-3">
              {NAV.map(({ href, label, icon: Icon }) => {
                const active = href === "/" ? path === "/" : path.startsWith(href);
                return (
                  <Link key={href} href={href} className={clsx("flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm",
                    active ? "bg-brand-50 font-medium text-brand-700" : "text-slate-600 hover:bg-slate-100")}>
                    <Icon size={16} /> {label}
                  </Link>
                );
              })}
            </nav>
            <div className="border-t border-slate-100 px-5 py-3 text-xs text-slate-500">
              Prototype · InfraCraft Labs<br />Not for production use.
            </div>
          </aside>
          <div className="flex min-w-0 flex-1 flex-col">
            <header className="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-slate-200 bg-white/90 px-6 py-2.5 backdrop-blur">
              <nav className="flex gap-2 overflow-x-auto md:hidden">
                {NAV.map(({ href, label }) => <Link key={href} href={href} className="whitespace-nowrap text-xs text-brand-700">{label}</Link>)}
              </nav>
              <div className="hidden text-xs text-slate-500 md:block">Read-only by default · every change is dry-run, approved, verified and audited</div>
              <div className="flex items-center gap-3">
                <Button small variant="secondary" onClick={() => setAssistant({ open: true })}><Bot size={14} /> Ask CloudGini</Button>
                {me && <span className="text-xs text-slate-600">{me.name} <Badge color="blue">{me.role}</Badge></span>}
              </div>
            </header>
            <main className="mx-auto w-full max-w-7xl flex-1 px-6 py-6">{children}</main>
          </div>
        </div>
        {assistant.open && <AssistantPanel recId={assistant.recId} onClose={() => setAssistant({ open: false })} />}
      </AssistantContext.Provider>
    </MeContext.Provider>
  );
}

type Answer = { answer: string; mode: string; model: string | null; redactions: number };

function AssistantPanel({ recId, onClose }: { recId?: string; onClose: () => void }) {
  const [q, setQ] = useState(recId ? "Explain this recommendation and what I should check before acting." : "What should I look at first?");
  const [log, setLog] = useState<{ q: string; a?: Answer; err?: string }[]>([]);
  const [busy, setBusy] = useState(false);
  async function ask() {
    if (q.trim().length < 2) return;
    setBusy(true);
    const question = q;
    try {
      const a = await api<Answer>("/assistant", { method: "POST", body: { question, recommendation_id: recId ?? null } });
      setLog((l) => [...l, { q: question, a }]);
    } catch (e) {
      setLog((l) => [...l, { q: question, err: (e as Error).message }]);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="fixed inset-y-0 right-0 z-30 flex w-full max-w-md flex-col border-l border-slate-200 bg-white shadow-2xl">
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
        <div>
          <div className="flex items-center gap-2 font-semibold"><Bot size={16} /> Ask CloudGini {recId && <Badge color="blue">{recId}</Badge>}</div>
          <div className="text-xs text-slate-500">Explains CloudGini&apos;s own analysis only. It can&apos;t change anything.</div>
        </div>
        <button onClick={onClose} className="rounded p-1 text-slate-500 hover:bg-slate-100" aria-label="Close"><X size={18} /></button>
      </div>
      <div className="flex-1 space-y-4 overflow-y-auto p-4 text-sm">
        {log.length === 0 && <p className="text-slate-500">Ask about savings, findings, evidence or next steps.</p>}
        {log.map((m, i) => (
          <div key={i} className="space-y-1.5">
            <div className="rounded-lg bg-brand-50 px-3 py-2 text-brand-700">{m.q}</div>
            {m.a && (
              <div className="rounded-lg bg-slate-50 px-3 py-2">
                <p className="whitespace-pre-wrap">{m.a.answer}</p>
                <div className="mt-1.5 text-[11px] text-slate-400">
                  {m.a.mode === "llm" ? `Model: ${m.a.model}` : "Template answer (no language model configured)"}
                  {m.a.redactions > 0 && ` · ${m.a.redactions} value(s) redacted before sending`}
                </div>
              </div>
            )}
            {m.err && <div className="rounded-lg bg-red-50 px-3 py-2 text-red-700">{m.err}</div>}
          </div>
        ))}
      </div>
      <form className="flex gap-2 border-t border-slate-100 p-3" onSubmit={(e) => { e.preventDefault(); ask(); }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} maxLength={2000}
          className="flex-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm outline-none focus:border-brand-500" />
        <Button type="submit" disabled={busy}>{busy ? "…" : "Ask"}</Button>
      </form>
    </div>
  );
}

