"use client";
import { KindPage } from "@/components/kind-page";
import { Card, Notice } from "@/components/ui";
import { useApi } from "@/lib/api";

type Check = { rule: string; name: string; open: number; resolved: number; total: number };

function Checks() {
  const { data } = useApi<Check[]>("/security/checks");
  return (
    <div className="mb-5 space-y-3">
      <Notice color="blue">Ten rules-based configuration checks. Findings describe facts and likely impact; they are <b>not</b> a compliance assessment.</Notice>
      <Card title="Checks">
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
          {(data ?? []).map((c) => (
            <div key={c.rule} className="rounded-lg border border-slate-200 p-3">
              <div className="text-xs font-medium text-slate-600">{c.name}</div>
              <div className={`mt-1 text-lg font-semibold ${c.open ? "text-red-700" : "text-emerald-700"}`}>{c.open ? `${c.open} open` : "pass"}</div>
              {c.resolved > 0 && <div className="text-xs text-emerald-700">{c.resolved} verified fixed</div>}
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

export default function SecurityPage() {
  return (
    <KindPage kind="security" title="Security" subtitle="Configuration findings with evidence, impact and remediation" intro={<Checks />}
      tabs={[
        { label: "Public access", rules: ["public_bucket", "public_database"] },
        { label: "Network", rules: ["open_ssh_rdp", "firewall_misconfiguration"] },
        { label: "Identity", rules: ["permissive_iam", "stale_sa_keys", "sa_excessive_permissions"] },
        { label: "Data protection", rules: ["encryption", "audit_logging", "unowned_sensitive"] },
      ]} />
  );
}
