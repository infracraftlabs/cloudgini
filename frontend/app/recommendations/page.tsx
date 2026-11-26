"use client";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { FilterBar, FilterState } from "@/components/filters";
import { RecTable } from "@/components/rec-table";
import { Card, ErrorBox, Loading, PageHeader } from "@/components/ui";
import { qs, useApi } from "@/lib/api";
import type { Recommendation } from "@/lib/types";

function List() {
  const sp = useSearchParams();
  const [f, setF] = useState<FilterState>({ state: sp.get("state") ?? undefined });
  const [kind, setKind] = useState("");
  const [severity, setSeverity] = useState("");
  const { data, error, loading } = useApi<Recommendation[]>(`/recommendations${qs({ ...f, kind, severity })}`);
  const sel = "rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm";
  return (
    <>
      <PageHeader title="Recommendations" subtitle="Every item, with its lifecycle: detected → reviewed → approved → executed → verified" />
      <div className="flex flex-wrap gap-2">
        <label className="flex flex-col text-xs text-slate-500">Module
          <select className={sel} value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">All</option><option value="cost">Cost</option><option value="cleanup">Cleanup</option><option value="security">Security</option>
          </select>
        </label>
        <label className="flex flex-col text-xs text-slate-500">Severity
          <select className={sel} value={severity} onChange={(e) => setSeverity(e.target.value)}>
            <option value="">All</option>{["critical", "high", "medium", "low", "info"].map((s) => <option key={s}>{s}</option>)}
          </select>
        </label>
        <FilterBar value={f} onChange={setF} />
      </div>
      {error && <ErrorBox msg={error} />}
      <Card title={`${data?.length ?? 0} recommendation(s)`}>{loading && !data ? <Loading /> : <RecTable recs={data ?? []} mode="all" />}</Card>
    </>
  );
}

export default function RecommendationsPage() {
  return <Suspense fallback={<Loading />}><List /></Suspense>;
}
