"use client";
import Link from "next/link";
import type { Recommendation } from "@/lib/types";
import { Badge, DataSourceBadge, Empty, Savings, SeverityBadge, StateBadge, Table, Td } from "./ui";

const short = (o: Record<string, unknown>) =>
  Object.entries(o).filter(([k]) => k !== "note").map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`).join(", ");

export function RecTable({ recs, mode }: { recs: Recommendation[]; mode: "cost" | "cleanup" | "security" | "all" }) {
  if (!recs.length) return <Empty>Nothing matches these filters.</Empty>;
  const head = ["ID", "Recommendation", "Resource"];
  if (mode === "cost") head.push("Current → recommended", "Evidence", "Savings", "Confidence / risk");
  if (mode === "cleanup") head.push("Checks", "Savings", "Risk");
  if (mode === "security") head.push("Evidence", "Severity");
  if (mode === "all") head.push("Kind", "Severity", "Savings");
  head.push("State", "Data");
  return (
    <Table head={head}>
      {recs.map((r) => (
        <tr key={r.id} className="hover:bg-slate-50">
          <Td><Link href={`/recommendations/${r.id}`} className="font-mono text-xs text-brand-700 hover:underline">{r.id}</Link></Td>
          <Td className="max-w-xs">
            <Link href={`/recommendations/${r.id}`} className="font-medium hover:text-brand-700">{r.title}</Link>
            <div className="text-xs text-slate-500">{r.summary}</div>
            {r.manual_review_reason && <div className="mt-0.5 text-xs text-orange-700">Manual review: {r.manual_review_reason}</div>}
          </Td>
          <Td className="text-xs">
            <div>{r.resource_name}</div>
            <div className="text-slate-500">{r.project} · {r.environment}</div>
          </Td>
          {mode === "cost" && <>
            <Td className="max-w-[14rem] text-xs"><span className="text-slate-500">{short(r.current_config)}</span><br />→ {short(r.recommended_config) || "—"}</Td>
            <Td className="max-w-[16rem] text-xs text-slate-600">
              {r.evidence.slice(0, 2).map((e, i) => <div key={i}>{e.label}: {String(e.value)}</div>)}
              {r.observation_days != null && <div className="text-slate-400">{r.observation_days}-day window</div>}
            </Td>
            <Td><Savings value={r.monthly_savings} basis={r.savings_basis} method={r.savings_method} /></Td>
            <Td className="text-xs">{r.confidence} / {r.risk}</Td>
          </>}
          {mode === "cleanup" && <>
            <Td className="text-xs">
              {r.checks.map((c) => (
                <div key={c.name} title={c.detail}>
                  <span className={c.status === "pass" ? "text-emerald-600" : c.status === "fail" ? "text-red-600" : "text-amber-600"}>
                    {c.status === "pass" ? "✓" : c.status === "fail" ? "✗" : "?"}</span> {c.name}
                </div>
              ))}
            </Td>
            <Td><Savings value={r.monthly_savings} basis={r.savings_basis} method={r.savings_method} /></Td>
            <Td className="text-xs">{r.risk}</Td>
          </>}
          {mode === "security" && <>
            <Td className="max-w-[18rem] text-xs text-slate-600">{r.evidence.slice(0, 3).map((e, i) => <div key={i}>{e.label}: {String(e.value)}</div>)}</Td>
            <Td><SeverityBadge s={r.severity} /></Td>
          </>}
          {mode === "all" && <>
            <Td><Badge>{r.kind}</Badge></Td>
            <Td><SeverityBadge s={r.severity} /></Td>
            <Td><Savings value={r.monthly_savings} basis={r.savings_basis} method={r.savings_method} /></Td>
          </>}
          <Td><StateBadge s={r.state} />{r.action_type && <div className="mt-1"><Badge color="blue" title="Has an automated, allow-listed action">{r.action_type}</Badge></div>}</Td>
          <Td><DataSourceBadge s={r.data_source} /></Td>
        </tr>
      ))}
    </Table>
  );
}
