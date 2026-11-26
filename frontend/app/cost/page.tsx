"use client";
import { KindPage } from "@/components/kind-page";
import { Notice } from "@/components/ui";

export default function CostPage() {
  return (
    <KindPage kind="cost" title="Cost Optimization" subtitle="Right-sizing and configuration changes backed by measured utilisation"
      intro={<div className="mb-4"><Notice color="blue">A recommendation needs utilisation metrics over the observation window. When metrics are missing or the window is too short, it becomes <b>requires manual review</b> and shows <b>no savings figure</b>.</Notice></div>}
      tabs={[
        { label: "VMs", rules: ["vm_rightsize", "vm_idle"] },
        { label: "Disks", rules: ["disk_type"] },
        { label: "Cloud SQL", rules: ["sql_rightsize"] },
        { label: "Load balancers", rules: ["lb_consolidate"] },
        { label: "GKE requests", rules: ["gke_requests"] },
        { label: "Storage classes", rules: ["storage_class"] },
      ]} />
  );
}
