"use client";
import Link from "next/link";
import { useState } from "react";
import { can, needs, useMe } from "@/components/shell";
import { Badge, Button, Card, DataSourceBadge, Empty, ErrorBox, KV, Loading, Notice, PageHeader, StateBadge } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import type { Account, Action, Recommendation } from "@/lib/types";

export default function RemediationPage() {
  const me = useMe();
  const actions = useApi<Action[]>("/actions");
  const recs = useApi<Recommendation[]>("/recommendations");
  const accounts = useApi<Account[]>("/accounts");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState<Record<string, string>>({});
  const [armed, setArmed] = useState<string | null>(null);
  const byId = Object.fromEntries((recs.data ?? []).map((r) => [r.id, r]));
  const allowed = can(me, "remediate");

  async function run(fn: () => Promise<Action | unknown>, ok: string) {
    setBusy(true);
    try {
      const res = await fn();
      const a = res as Action;
      if (a && a.state === "failed") setMsg({ ok: false, text: `${a.id} failed: ${a.error}` });
      else setMsg({ ok: true, text: ok });
    } catch (e) { setMsg({ ok: false, text: (e as Error).message }); }
    setBusy(false);
    setArmed(null);
    actions.reload(); recs.reload(); accounts.reload();
  }

  if (actions.error) return <ErrorBox msg={actions.error} />;
  if (!actions.data || !recs.data) return <Loading />;
  const ready = recs.data.filter((r) => r.action_type && r.state === "reviewed" && !actions.data!.some((a) => a.recommendation_id === r.id && ["planned", "approved"].includes(a.state)));
  const waiting = recs.data.filter((r) => r.action_type && r.state === "detected");
  const planned = actions.data.filter((a) => a.state === "planned");
  const approved = actions.data.filter((a) => a.state === "approved");
  const history = actions.data.filter((a) => !["planned", "approved"].includes(a.state));
  const readOnly = (accounts.data ?? []).filter((a) => !a.remediation_enabled);

  const PlanBox = ({ a }: { a: Action }) => (
    <div className="grid gap-3 text-xs sm:grid-cols-2">
      <div><div className="mb-1 font-medium text-slate-500">Steps</div><ol className="list-decimal pl-4">{a.plan.steps.map((s, i) => <li key={i}>{s}</li>)}</ol></div>
      <div><div className="mb-1 font-medium text-slate-500">Preconditions (re-checked at execution)</div><ul className="list-disc pl-4">{a.plan.preconditions.map((s, i) => <li key={i}>{s}</li>)}</ul></div>
      <div><div className="mb-1 font-medium text-slate-500">Before</div><KV data={a.plan.before} /></div>
      <div><div className="mb-1 font-medium text-slate-500">After</div><KV data={a.plan.after} /></div>
      <div className="sm:col-span-2"><div className="mb-1 font-medium text-slate-500">Rollback</div><p className={a.reversible ? "" : "font-medium text-red-700"}>{a.rollback}</p></div>
    </div>
  );

  const Head = ({ a }: { a: Action }) => {
    const r = byId[a.recommendation_id];
    return (
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs">{a.id}</span><StateBadge s={a.state} /><b className="text-sm">{a.action_type}</b>
        <span className="text-sm">on {r?.resource_name}</span><span className="text-xs text-slate-500">({r?.project} · {r?.environment})</span>
        {a.destructive ? <Badge color="red">IRREVERSIBLE</Badge> : <Badge color="green">reversible</Badge>}
        <DataSourceBadge s={a.data_source} />
        <Link href={`/recommendations/${a.recommendation_id}`} className="text-xs text-brand-700 hover:underline">{a.recommendation_id}</Link>
      </div>
    );
  };

  return (
    <>
      <PageHeader title="Remediation Center" subtitle="Dry-run → explicit approval → execution → verification, all audited" />
      <div className="mb-4 space-y-2">
        <Notice color="blue">Only allow-listed, validated actions: stop or resize a non-production VM, release an unused IP, restrict a firewall rule, remove public bucket access. No production changes, no deletions of data, no shell or arbitrary API calls.</Notice>
        {readOnly.length > 0 && <Notice>Read-only accounts (execution will be refused): {readOnly.map((a) => a.name).join(", ")}. An admin can enable remediation on <Link className="underline" href="/accounts">Cloud Accounts</Link>.</Notice>}
        {!allowed && <Notice>{needs("remediate")} (your role: {me?.role}). You can view everything here.</Notice>}
        {msg && (msg.ok ? <Notice color="green">{msg.text}</Notice> : <ErrorBox msg={msg.text} />)}
      </div>
      <div className="space-y-5">
        <Card title={`1. Ready for dry-run (${ready.length})`}>
          {ready.length ? (
            <ul className="divide-y divide-slate-100">
              {ready.map((r) => (
                <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
                  <span><Link href={`/recommendations/${r.id}`} className="font-mono text-xs text-brand-700">{r.id}</Link> {r.title} <Badge color="blue">{r.action_type}</Badge></span>
                  <Button small disabled={busy || !allowed} title={!allowed ? needs("remediate") : undefined}
                    onClick={() => run(() => api(`/recommendations/${r.id}/actions`, { method: "POST", body: {} }), "Dry-run created: review the plan below")}>Run dry-run</Button>
                </li>
              ))}
            </ul>
          ) : <Empty>Nothing reviewed and ready. {waiting.length > 0 && <>{waiting.length} item(s) with an automated action are waiting for review on <Link href="/recommendations?state=detected" className="text-brand-700 underline">Recommendations</Link>.</>}</Empty>}
        </Card>
        <Card title={`2. Planned: waiting for approval (${planned.length})`}>
          {planned.length ? planned.map((a) => (
            <div key={a.id} className="mb-3 rounded-lg border border-slate-200 p-3">
              <Head a={a} /><PlanBox a={a} />
              <div className="mt-3 flex flex-wrap items-center gap-2">
                {a.destructive && (
                  <input placeholder={`Type ${byId[a.recommendation_id]?.resource_name} to confirm`} value={confirm[a.id] ?? ""}
                    onChange={(e) => setConfirm({ ...confirm, [a.id]: e.target.value })}
                    className="rounded-lg border border-red-300 px-2 py-1 text-sm" />
                )}
                <Button small variant={a.destructive ? "danger" : "primary"} disabled={busy || !allowed || (a.destructive && confirm[a.id] !== byId[a.recommendation_id]?.resource_name)}
                  onClick={() => run(() => api(`/actions/${a.id}/approve`, { method: "POST", body: { confirm: confirm[a.id] ?? null } }), `${a.id} approved`)}>Approve</Button>
                <Button small variant="secondary" disabled={busy || !allowed} onClick={() => run(() => api(`/actions/${a.id}/cancel`, { method: "POST" }), `${a.id} cancelled`)}>Cancel</Button>
              </div>
            </div>
          )) : <Empty>No planned actions.</Empty>}
        </Card>
        <Card title={`3. Approved: ready to execute (${approved.length})`}>
          {approved.length ? approved.map((a) => (
            <div key={a.id} className="mb-3 rounded-lg border border-slate-200 p-3">
              <Head a={a} /><p className="mb-2 text-xs text-slate-500">Approved by {a.approved_by}. Execution re-reads the resource, re-checks the environment and compares it with the dry-run before changing anything; verification runs straight after.</p>
              <PlanBox a={a} />
              <div className="mt-3 flex gap-2">
                {armed === a.id ? (
                  <>
                    <Button small variant="danger" disabled={busy} onClick={() => run(() => api(`/actions/${a.id}/execute`, { method: "POST" }), `${a.id} executed and verified`)}>Confirm: execute now</Button>
                    <Button small variant="secondary" onClick={() => setArmed(null)}>Back</Button>
                  </>
                ) : (
                  <Button small disabled={busy || !allowed} title={!allowed ? needs("remediate") : undefined} onClick={() => setArmed(a.id)}>Execute…</Button>
                )}
                <Button small variant="secondary" disabled={busy || !allowed} onClick={() => run(() => api(`/actions/${a.id}/cancel`, { method: "POST" }), `${a.id} cancelled`)}>Cancel</Button>
              </div>
            </div>
          )) : <Empty>No approved actions.</Empty>}
        </Card>
        <Card title={`4. History (${history.length})`}>
          {history.length ? history.map((a) => (
            <div key={a.id} className="mb-3 rounded-lg border border-slate-200 p-3">
              <Head a={a} />
              <p className="text-xs text-slate-500">Requested by {a.requested_by} · approved by {a.approved_by ?? "—"} · executed by {a.executed_by ?? "—"}</p>
              {a.error && <div className="mt-2"><ErrorBox msg={a.error} /></div>}
              {a.verification && <div className="mt-2 text-xs"><b>Verification</b> <KV data={a.verification} /></div>}
              {a.state === "failed" && <p className="mt-2 text-xs"><b>Rollback / recovery:</b> {a.rollback}</p>}
            </div>
          )) : <Empty>No executed actions yet.</Empty>}
        </Card>
      </div>
    </>
  );
}
