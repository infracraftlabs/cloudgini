"use client";
import { Bot } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { can, needs, useAssistant, useMe } from "@/components/shell";
import { Badge, Button, Card, DataSourceBadge, ErrorBox, KV, Loading, Notice, PageHeader, Savings, SeverityBadge, StateBadge, Table, Td } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import type { Account, Action, AuditEvent, Recommendation } from "@/lib/types";

type Detail = {
  recommendation: Recommendation; account: Account; actions: Action[]; audit: AuditEvent[]; allowed_transitions: string[];
  resource: { name: string; resource_type: string; project: string; region: string | null; environment: string; owner: string | null;
              labels: Record<string, string>; config: Record<string, unknown>; monthly_cost: number | null; cost_basis: string } | null;
};

const LABEL: Record<string, string> = {
  reviewed: "Mark reviewed", rejected: "Reject", requires_manual_review: "Send to manual review",
  approved: "Approve procedure", detected: "Reopen",
};

export default function RecommendationDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const me = useMe();
  const ask = useAssistant();
  const { data, error, reload } = useApi<Detail>(`/recommendations/${id}`);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  async function run(fn: () => Promise<unknown>, ok: string) {
    setBusy(true);
    try { await fn(); setMsg({ ok: true, text: ok }); } catch (e) { setMsg({ ok: false, text: (e as Error).message }); }
    setBusy(false);
    reload();
  }

  if (error) return <ErrorBox msg={error} />;
  if (!data) return <Loading />;
  const r = data.recommendation;
  const transitionPerm = (t: string) => (t === "approved" ? "remediate" : "review");

  return (
    <>
      <PageHeader title={r.title}
        subtitle={<span className="flex flex-wrap items-center gap-2"><span className="font-mono">{r.id}</span> · {r.kind} · rule <span className="font-mono">{r.rule}</span></span>}
        actions={<><DataSourceBadge s={r.data_source} /><SeverityBadge s={r.severity} /><StateBadge s={r.state} />
          <Button small variant="secondary" onClick={() => ask(r.id)}><Bot size={14} /> Explain</Button></>} />
      {msg && <div className="mb-4">{msg.ok ? <Notice color="green">{msg.text}</Notice> : <ErrorBox msg={msg.text} />}</div>}
      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <Card title="Summary">
            <p className="text-sm">{r.summary}</p>
            {r.manual_review_reason && <div className="mt-3"><Notice>Requires manual review: {r.manual_review_reason}</Notice></div>}
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <div><div className="mb-1 text-xs font-medium text-slate-500">Current</div><KV data={r.current_config} /></div>
              <div><div className="mb-1 text-xs font-medium text-slate-500">Recommended</div><KV data={r.recommended_config} /></div>
            </div>
          </Card>
          <Card title="Evidence">
            {r.evidence.length ? (
              <Table head={["What", "Value", "Source"]}>
                {r.evidence.map((e, i) => (
                  <tr key={i}><Td className="text-xs font-medium">{e.label}</Td><Td className="text-xs">{typeof e.value === "object" ? JSON.stringify(e.value) : String(e.value)}</Td><Td className="text-xs text-slate-500">{e.source}</Td></tr>
                ))}
              </Table>
            ) : <p className="text-sm text-slate-500">No evidence collected.</p>}
            {r.observation_days != null && <p className="mt-2 text-xs text-slate-500">Observation period: {r.observation_days} days</p>}
          </Card>
          {r.checks.length > 0 && (
            <Card title="Safety checks (dependencies, retention, backup, ownership)">
              <ul className="space-y-1 text-sm">
                {r.checks.map((c) => (
                  <li key={c.name}><Badge color={c.status === "pass" ? "green" : c.status === "fail" ? "red" : "amber"}>{c.status}</Badge> <b>{c.name}</b>: {c.detail}</li>
                ))}
              </ul>
            </Card>
          )}
          <Card title="Impact and procedure">
            {r.impact && <p className="mb-3 text-sm">{r.impact}</p>}
            <ol className="list-decimal space-y-1 pl-5 text-sm">{r.procedure.map((p, i) => <li key={i} className="break-words">{p}</li>)}</ol>
          </Card>
          {data.actions.length > 0 && (
            <Card title="Remediation actions" actions={<Link href="/remediation" className="text-xs text-brand-700 hover:underline">Remediation Center</Link>}>
              <ul className="space-y-2 text-sm">
                {data.actions.map((a) => (
                  <li key={a.id} className="rounded-lg border border-slate-200 p-2">
                    <div className="flex flex-wrap items-center gap-2"><span className="font-mono text-xs">{a.id}</span><StateBadge s={a.state} /><span>{a.action_type}</span>
                      {a.destructive && <Badge color="red">irreversible</Badge>}</div>
                    {a.error && <p className="mt-1 text-xs text-red-700">{a.error}</p>}
                    {a.verification && <div className="mt-1 text-xs">Verification: <KV data={a.verification} /></div>}
                  </li>
                ))}
              </ul>
            </Card>
          )}
          <Card title="Audit trail">
            {data.audit.length ? (
              <ul className="space-y-1 text-xs">
                {data.audit.map((e) => (
                  <li key={e.id} className="flex flex-wrap gap-2">
                    <span className="text-slate-400">{new Date(e.ts).toLocaleString()}</span>
                    <Badge color={e.outcome === "success" ? "green" : e.outcome === "info" ? "gray" : "red"}>{e.outcome}</Badge>
                    <span className="font-mono">{e.event}</span><span>{e.actor} ({e.role})</span>
                    {"to" in e.details && <span className="text-slate-500">→ {String(e.details.to)}</span>}
                    {"error" in e.details && <span className="text-red-600">{String(e.details.error)}</span>}
                  </li>
                ))}
              </ul>
            ) : <p className="text-sm text-slate-500">No events yet.</p>}
          </Card>
        </div>
        <div className="space-y-5">
          <Card title="Savings">
            <Savings value={r.monthly_savings} basis={r.savings_basis} method={r.savings_method} />
            <p className="mt-2 text-xs text-slate-500">{r.savings_method}</p>
            <dl className="mt-3 grid grid-cols-2 gap-1 text-xs">
              <dt className="text-slate-500">Confidence</dt><dd>{r.confidence}</dd>
              <dt className="text-slate-500">Risk</dt><dd>{r.risk}</dd>
            </dl>
          </Card>
          <Card title="Lifecycle">
            <div className="flex flex-wrap gap-2">
              {data.allowed_transitions.map((t) => (
                <Button key={t} small variant={t === "rejected" ? "secondary" : "primary"} disabled={busy || !can(me, transitionPerm(t))}
                  title={!can(me, transitionPerm(t)) ? needs(transitionPerm(t)) : undefined}
                  onClick={() => run(() => api(`/recommendations/${r.id}/transition`, { method: "POST", body: { to: t } }), `Moved to ${t.replaceAll("_", " ")}`)}>
                  {LABEL[t] ?? t}
                </Button>
              ))}
              {data.allowed_transitions.length === 0 && r.state !== "approved" && r.state !== "executed" &&
                <p className="text-xs text-slate-500">No manual transitions from this state.</p>}
            </div>
            {r.action_type && r.state === "reviewed" && (
              <div className="mt-3 border-t border-slate-100 pt-3">
                <p className="mb-2 text-xs text-slate-600">Automated action: <b>{r.action_type}</b>. Start with a dry-run; nothing changes until it is approved and executed.</p>
                <Button small disabled={busy || !can(me, "remediate")} title={!can(me, "remediate") ? needs("remediate") : undefined}
                  onClick={() => run(async () => { await api(`/recommendations/${r.id}/actions`, { method: "POST", body: {} }); router.push("/remediation"); }, "Dry-run created")}>
                  Run dry-run
                </Button>
              </div>
            )}
            {!r.action_type && r.state === "approved" && (
              <div className="mt-3 space-y-2 border-t border-slate-100 pt-3">
                <p className="text-xs text-slate-600">Carry out the procedure yourself, then record it. CloudGini re-reads the resource and only marks it verified if the rule no longer fires.</p>
                <textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="What was done (e.g. change ticket)" maxLength={1000}
                  className="w-full rounded-lg border border-slate-300 px-2 py-1 text-sm" rows={2} />
                <Button small disabled={busy || note.length < 3 || !can(me, "remediate")} title={!can(me, "remediate") ? needs("remediate") : undefined}
                  onClick={() => run(() => api(`/recommendations/${r.id}/manual-execution`, { method: "POST", body: { note } }), "Recorded and verified (see state)")}>
                  Record as done and verify
                </Button>
              </div>
            )}
            {r.state === "executed" && (
              <div className="mt-3 border-t border-slate-100 pt-3">
                <Button small disabled={busy || !can(me, "remediate")}
                  onClick={() => run(() => api(r.action_type ? `/actions/${data.actions.at(-1)?.id}/verify` : `/recommendations/${r.id}/verify`, { method: "POST" }), "Verification ran")}>
                  Verify now
                </Button>
              </div>
            )}
            {r.verification && (
              <div className="mt-3 border-t border-slate-100 pt-3 text-xs">
                <div className="mb-1 font-medium">Last verification: {r.verification.ok ? <Badge color="green">passed</Badge> : <Badge color="red">failed</Badge>}</div>
                <KV data={r.verification} />
              </div>
            )}
          </Card>
          {data.resource && (
            <Card title="Resource">
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
                <dt className="text-slate-500">Name</dt><dd className="break-all">{data.resource.name}</dd>
                <dt className="text-slate-500">Type</dt><dd>{data.resource.resource_type}</dd>
                <dt className="text-slate-500">Project</dt><dd>{data.resource.project}</dd>
                <dt className="text-slate-500">Region</dt><dd>{data.resource.region ?? "—"}</dd>
                <dt className="text-slate-500">Environment</dt><dd>{data.resource.environment}</dd>
                <dt className="text-slate-500">Owner</dt><dd>{data.resource.owner ?? <span className="text-orange-700">none</span>}</dd>
                <dt className="text-slate-500">Cost (30 d)</dt><dd>{data.resource.monthly_cost != null ? `$${data.resource.monthly_cost} (${data.resource.cost_basis})` : "no billing data"}</dd>
                <dt className="text-slate-500">Account</dt><dd>{data.account.name}</dd>
              </dl>
              <details className="mt-3 text-xs"><summary className="cursor-pointer text-slate-500">Configuration and labels</summary>
                <div className="mt-2 space-y-2"><KV data={data.resource.labels} /><KV data={data.resource.config} /></div>
              </details>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
