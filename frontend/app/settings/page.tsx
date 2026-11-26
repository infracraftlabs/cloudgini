"use client";
import { useEffect, useState } from "react";
import { can, needs, useMe } from "@/components/shell";
import { Badge, Button, Card, ErrorBox, Loading, Notice, PageHeader, Table, Td } from "@/components/ui";
import { api, useApi } from "@/lib/api";

type S = {
  thresholds: Record<string, number>; defaults: Record<string, number>;
  assistant: { mode: string; model: string | null }; rate_limit_per_minute: number; sensitive_rate_limit_per_minute: number;
  gcp_billing_table_configured: boolean; roles: Record<string, string[]>;
};

export default function SettingsPage() {
  const me = useMe();
  const { data, error, reload } = useApi<S>("/settings");
  const [t, setT] = useState<Record<string, number>>({});
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  useEffect(() => { if (data) setT(data.thresholds); }, [data]);
  if (error) return <ErrorBox msg={error} />;
  if (!data) return <Loading />;
  async function save(values: Record<string, number>) {
    try { await api("/settings/thresholds", { method: "PUT", body: values }); setMsg({ ok: true, text: "Saved. Applies from the next scan." }); }
    catch (e) { setMsg({ ok: false, text: (e as Error).message }); }
    reload();
  }
  async function signOut() { await fetch("/api/session", { method: "DELETE" }); window.location.href = "/login"; }
  const admin = can(me, "manage");
  return (
    <>
      <PageHeader title="Settings" actions={<Button variant="secondary" onClick={signOut}>Sign out</Button>} />
      {msg && <div className="mb-4">{msg.ok ? <Notice color="green">{msg.text}</Notice> : <ErrorBox msg={msg.text} />}</div>}
      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Analysis thresholds" actions={<>
          <Button small variant="secondary" disabled={!admin} title={!admin ? needs("manage") : undefined} onClick={() => save(data.defaults)}>Reset to defaults</Button>
          <Button small disabled={!admin} title={!admin ? needs("manage") : undefined} onClick={() => save(t)}>Save</Button></>}>
          <div className="grid grid-cols-2 gap-3">
            {Object.entries(t).map(([k, v]) => (
              <label key={k} className="text-xs text-slate-600">{k.replaceAll("_", " ")}
                <input type="number" step="any" value={v} disabled={!admin} onChange={(e) => setT({ ...t, [k]: Number(e.target.value) })}
                  className="mt-0.5 w-full rounded-lg border border-slate-300 px-2 py-1 text-sm disabled:bg-slate-50" />
              </label>
            ))}
          </div>
        </Card>
        <div className="space-y-5">
          <Card title="You">
            <p className="text-sm">{me?.name} <Badge color="blue">{me?.role}</Badge></p>
            <p className="mt-1 text-xs text-slate-500">Permissions: {me?.permissions.join(", ")}</p>
          </Card>
          <Card title="Assistant">
            <p className="text-sm">Mode: <Badge color={data.assistant.mode === "llm" ? "green" : "gray"}>{data.assistant.mode}</Badge> {data.assistant.model}</p>
            <p className="mt-1 text-xs text-slate-500">Set ANTHROPIC_API_KEY on the backend to use a language model. Without it, answers come from templates. The assistant only sees CloudGini&apos;s own analysis (redacted) and can&apos;t change anything.</p>
          </Card>
          <Card title="Platform">
            <ul className="space-y-1 text-sm">
              <li>Rate limit: {data.rate_limit_per_minute}/min ({data.sensitive_rate_limit_per_minute}/min for scan, approve, execute, assistant)</li>
              <li>GCP billing export: {data.gcp_billing_table_configured ? <Badge color="green">configured</Badge> : <Badge>not configured</Badge>}</li>
            </ul>
          </Card>
          <Card title="Roles (least privilege)">
            <Table head={["Role", "Permissions"]}>
              {Object.entries(data.roles).map(([r, p]) => <tr key={r}><Td className="font-medium">{r}</Td><Td className="text-xs">{p.join(", ")}</Td></tr>)}
            </Table>
            <p className="mt-2 text-xs text-slate-500">Admins manage settings and accounts but can&apos;t remediate; operators remediate but can&apos;t change settings.</p>
          </Card>
        </div>
      </div>
    </>
  );
}
