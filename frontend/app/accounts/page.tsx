"use client";
import { useState } from "react";
import { can, needs, useMe } from "@/components/shell";
import { Badge, Button, Card, DataSourceBadge, ErrorBox, Loading, Notice, PageHeader, Table, Td } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import type { Account } from "@/lib/types";

export default function AccountsPage() {
  const me = useMe();
  const { data, error, reload } = useApi<Account[]>("/accounts");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);

  async function run(fn: () => Promise<unknown>, ok: (r: unknown) => string) {
    setBusy(true);
    try { setMsg({ ok: true, text: ok(await fn()) }); } catch (e) { setMsg({ ok: false, text: (e as Error).message }); }
    setBusy(false); setConfirmReset(false); reload();
  }
  if (error) return <ErrorBox msg={error} />;
  if (!data) return <Loading />;
  return (
    <>
      <PageHeader title="Cloud Accounts" subtitle="Connected accounts, data source and remediation mode"
        actions={<>
          <Button variant="secondary" onClick={() => setShowAdd(!showAdd)}>Connect a GCP project</Button>
          {confirmReset ? (
            <><Button variant="danger" disabled={busy} onClick={() => run(() => api("/demo/reset", { method: "POST" }), () => "Simulated demo reset to its initial state and re-scanned")}>Confirm reset</Button>
              <Button variant="ghost" onClick={() => setConfirmReset(false)}>Back</Button></>
          ) : (
            <Button variant="secondary" disabled={!can(me, "manage")} title={!can(me, "manage") ? needs("manage") : "Restore the simulated estate and clear its recommendations (audit log is kept)"}
              onClick={() => setConfirmReset(true)}>Reset simulated demo</Button>
          )}
        </>} />
      {msg && <div className="mb-4">{msg.ok ? <Notice color="green">{msg.text}</Notice> : <ErrorBox msg={msg.text} />}</div>}
      {showAdd && (
        <div className="mb-5"><Card title="Connect a GCP project (read-only)">
          <ol className="list-decimal space-y-1 pl-5 text-sm">
            <li>Create a service account for CloudGini and grant only the read-only roles in <code>docs/gcp-setup.md</code>. No keys: CloudGini uses Application Default Credentials (the Cloud Run service account, or <code>gcloud auth application-default login</code> locally).</li>
            <li>Set <code>CLOUDGINI_GCP_PROJECTS=&lt;project-id&gt;</code> (comma-separated for several) and, for cost data, <code>CLOUDGINI_GCP_BILLING_TABLE</code> to your BigQuery billing export table.</li>
            <li>Restart the backend. The project appears here as <Badge color="green">REAL</Badge>, read-only. Click <b>Scan now</b>.</li>
          </ol>
          <p className="mt-2 text-xs text-slate-500">Accounts are configured on the server, never through this page, so no credentials are stored in the database or sent through the browser.</p>
        </Card></div>
      )}
      <Card>
        <Table head={["Account", "Provider", "Data", "Status", "Last scan", "Remediation", ""]}>
          {data.map((a) => (
            <tr key={a.id}>
              <Td><div className="font-medium">{a.name}</div><div className="font-mono text-xs text-slate-500">{a.id} · {a.scope_id}</div></Td>
              <Td>{a.provider}</Td>
              <Td><DataSourceBadge s={a.data_source} /></Td>
              <Td><Badge color={a.status === "ok" ? "green" : a.status === "error" ? "red" : "gray"}>{a.status}</Badge>
                {a.status_detail && <div className="mt-1 max-w-xs text-xs text-slate-500">{a.status_detail}</div>}</Td>
              <Td className="text-xs">{a.last_scan_at ? new Date(a.last_scan_at).toLocaleString() : "never"}</Td>
              <Td>
                {a.remediation_enabled ? <Badge color="amber">enabled</Badge> : <Badge>read-only</Badge>}
                <div className="mt-1">
                  <Button small variant="ghost" disabled={busy || !can(me, "manage")} title={!can(me, "manage") ? needs("manage") : undefined}
                    onClick={() => run(() => api(`/accounts/${a.id}`, { method: "PATCH", body: { remediation_enabled: !a.remediation_enabled } }),
                      () => `Remediation ${a.remediation_enabled ? "disabled" : "enabled"} for ${a.name}`)}>
                    {a.remediation_enabled ? "Make read-only" : "Enable remediation"}
                  </Button>
                </div>
              </Td>
              <Td>
                <Button small disabled={busy || !can(me, "scan")} title={!can(me, "scan") ? needs("scan") : undefined}
                  onClick={() => run(() => api(`/accounts/${a.id}/scan`, { method: "POST" }), (r) => {
                    const s = r as Record<string, number>;
                    return `Scan finished: ${s.resources} resources, ${s.new} new, ${s.updated} updated, ${s.reopened} reopened`;
                  })}>{busy ? "Working…" : "Scan now"}</Button>
              </Td>
            </tr>
          ))}
        </Table>
      </Card>
    </>
  );
}
