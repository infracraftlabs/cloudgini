"use client";
import clsx from "clsx";
import { ReactNode, useState } from "react";
import { FilterBar, FilterState } from "./filters";
import { RecTable } from "./rec-table";
import { Card, ErrorBox, Loading, PageHeader } from "./ui";
import { money, qs, useApi } from "@/lib/api";
import type { Recommendation } from "@/lib/types";

export function KindPage({ kind, title, subtitle, tabs, intro }: {
  kind: "cost" | "cleanup" | "security"; title: string; subtitle: string;
  tabs: { label: string; rules: string[] }[]; intro?: ReactNode;
}) {
  const [f, setF] = useState<FilterState>({ state: "open" });
  const [tab, setTab] = useState(0);
  const { data, error, loading } = useApi<Recommendation[]>(`/recommendations${qs({ ...f, kind })}`);
  const all = [{ label: "All", rules: [] as string[] }, ...tabs];
  const shown = (data ?? []).filter((r) => !all[tab].rules.length || all[tab].rules.includes(r.rule));
  const est = shown.reduce((s, r) => s + (r.savings_basis === "estimated" ? r.monthly_savings ?? 0 : 0), 0);
  return (
    <>
      <PageHeader title={title} subtitle={subtitle} />
      {intro}
      <FilterBar value={f} onChange={setF} />
      <div className="mb-3 flex flex-wrap gap-1">
        {all.map((t, i) => {
          const n = (data ?? []).filter((r) => !t.rules.length || t.rules.includes(r.rule)).length;
          return (
            <button key={t.label} onClick={() => setTab(i)} className={clsx("rounded-lg px-3 py-1.5 text-sm",
              tab === i ? "bg-brand-600 text-white" : "bg-white text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50")}>
              {t.label} <span className="opacity-70">({n})</span>
            </button>
          );
        })}
      </div>
      {error && <ErrorBox msg={error} />}
      <Card title={`${shown.length} item(s)`} actions={kind !== "security" && <span className="text-xs text-slate-500">Estimated savings shown: <b>{money(est)}/mo</b></span>}>
        {loading && !data ? <Loading /> : <RecTable recs={shown} mode={kind} />}
      </Card>
    </>
  );
}
