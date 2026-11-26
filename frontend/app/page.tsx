"use client";
import Link from "next/link";
import { useState } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { FilterBar, FilterState } from "@/components/filters";
import { Badge, Card, DataSourceBadge, Empty, ErrorBox, Kpi, Loading, Notice, PageHeader } from "@/components/ui";
import { money, qs, useApi } from "@/lib/api";
import type { AuditEvent } from "@/lib/types";

type Overview = {
  data_sources: string[];
  kpis: Record<string, number> & { cost_basis: string[] };
  cost_trend: { day: string; cost: number }[];
  cost_by_service: { service: string; cost: number }[];
  severity_breakdown: { severity: string; count: number }[];
  state_breakdown: { state: string; count: number }[];
  savings_by_kind: { kind: string; estimated: number }[];
  recent_activity: AuditEvent[];
};

const SEV_COLORS: Record<string, string> = { critical: "#dc2626", high: "#ea580c", medium: "#d97706", low: "#2f6fed", info: "#94a3b8" };

export default function OverviewPage() {
  const [f, setF] = useState<FilterState>({});
  const { data, error, loading } = useApi<Overview>(`/overview${qs(f)}`);
  return (
    <>
      <PageHeader title="Overview" subtitle="Cost, waste and security across your connected accounts"
        actions={data?.data_sources.map((s) => <DataSourceBadge key={s} s={s} />)} />
      <FilterBar value={f} onChange={setF} />
      {error && <ErrorBox msg={error} />}
      {loading && !data && <Loading />}
      {data && (
        <div className="space-y-5">
          {data.data_sources.includes("simulated") && (
            <Notice>Showing <b>simulated</b> data: a synthetic estate with planted issues and a synthetic price table. No figure here is real cloud pricing.</Notice>
          )}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Kpi label="Spend, last 30 days" value={money(data.kpis.monthly_cost_30d)} hint={`basis: ${data.kpis.cost_basis.join(", ") || "no billing data"}`} />
            <Kpi label="Estimated savings / month" value={money(data.kpis.estimated_monthly_savings)} color="text-emerald-700"
              hint={<>{data.kpis.recommendations_without_savings_figure} cost/cleanup items have <b>no figure</b> (missing evidence)</>} />
            <Kpi label="Verified savings / month" value={money(data.kpis.verified_monthly_savings)}
              hint="Needs billing data after a change; none yet" />
            <Kpi label="Open security findings" value={data.kpis.security_open} color="text-red-700"
              hint={`${data.kpis.critical_high_open} critical or high`} />
            <Kpi label="Cleanup candidates" value={data.kpis.cleanup_candidates} hint="never deleted on age or low use alone" />
            <Kpi label="Needs manual review" value={data.kpis.manual_review} color="text-orange-700" />
            <Kpi label="Verified fixes" value={data.kpis.verified} color="text-emerald-700" />
            <Kpi label="Resources" value={data.kpis.resources} />
          </div>
          <div className="grid gap-5 lg:grid-cols-3">
            <Card title="Daily cost trend" className="lg:col-span-2">
              {data.cost_trend.length ? (
                <ResponsiveContainer width="100%" height={240}>
                  <AreaChart data={data.cost_trend} margin={{ left: 0, right: 8, top: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="day" tick={{ fontSize: 11 }} tickFormatter={(d: string) => d.slice(5)} minTickGap={24} />
                    <YAxis tick={{ fontSize: 11 }} width={48} tickFormatter={(v: number) => `$${Math.round(v)}`} />
                    <Tooltip formatter={(v) => money(Number(v))} />
                    <Area type="monotone" dataKey="cost" stroke="#2259d1" fill="#d9eaff" strokeWidth={2} />
                  </AreaChart>
                </ResponsiveContainer>
              ) : <Empty>No billing data for this selection.</Empty>}
            </Card>
            <Card title="Open security findings by severity">
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={data.severity_breakdown} margin={{ left: -16, right: 8, top: 4 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                  <XAxis dataKey="severity" tick={{ fontSize: 11 }} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                    {data.severity_breakdown.map((d) => <Cell key={d.severity} fill={SEV_COLORS[d.severity]} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </Card>
          </div>
          <div className="grid gap-5 lg:grid-cols-3">
            <Card title="Spend by service (30 days)">
              {data.cost_by_service.length ? (
                <ul className="space-y-2 text-sm">
                  {data.cost_by_service.map((s) => (
                    <li key={s.service} className="flex justify-between"><span>{s.service}</span><span className="tabular-nums">{money(s.cost)}</span></li>
                  ))}
                </ul>
              ) : <Empty>No billing data.</Empty>}
            </Card>
            <Card title="Estimated savings by module">
              {data.savings_by_kind.length ? (
                <ul className="space-y-2 text-sm">
                  {data.savings_by_kind.map((s) => (
                    <li key={s.kind} className="flex justify-between">
                      <Link className="capitalize text-brand-700 hover:underline" href={s.kind === "cost" ? "/cost" : "/cleanup"}>{s.kind}</Link>
                      <span className="tabular-nums">{money(s.estimated)} <Badge color="amber">estimated</Badge></span>
                    </li>
                  ))}
                </ul>
              ) : <Empty>No estimated savings.</Empty>}
            </Card>
            <Card title="Recommendation states">
              <ul className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
                {data.state_breakdown.map((s) => (
                  <li key={s.state} className="flex justify-between">
                    <Link href={`/recommendations?state=${s.state}`} className="text-slate-600 hover:text-brand-700">{s.state.replaceAll("_", " ")}</Link>
                    <span className="tabular-nums">{s.count}</span>
                  </li>
                ))}
              </ul>
            </Card>
          </div>
          <Card title="Recent actions" actions={<Link href="/audit" className="text-xs text-brand-700 hover:underline">Full audit history</Link>}>
            {data.recent_activity.length ? (
              <ul className="divide-y divide-slate-100 text-sm">
                {data.recent_activity.map((e) => (
                  <li key={e.id} className="flex flex-wrap items-center gap-2 py-1.5">
                    <span className="text-xs text-slate-400">{new Date(e.ts).toLocaleString()}</span>
                    <Badge color={e.outcome === "success" ? "green" : e.outcome === "info" ? "gray" : "red"}>{e.outcome}</Badge>
                    <span className="font-mono text-xs">{e.event}</span>
                    <Link href={e.target_type === "recommendation" ? `/recommendations/${e.target_id}` : "/remediation"} className="text-brand-700 hover:underline">{e.target_id}</Link>
                    <span className="text-xs text-slate-500">by {e.actor}</span>
                  </li>
                ))}
              </ul>
            ) : <Empty>No actions yet. Review a recommendation to get started.</Empty>}
          </Card>
        </div>
      )}
    </>
  );
}
