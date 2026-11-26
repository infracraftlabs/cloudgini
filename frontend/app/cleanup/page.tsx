"use client";
import { KindPage } from "@/components/kind-page";
import { Notice } from "@/components/ui";

export default function CleanupPage() {
  return (
    <KindPage kind="cleanup" title="Resource Cleanup" subtitle="Unused and orphaned resources, with dependency, retention, backup and ownership checks"
      intro={<div className="mb-4"><Notice color="blue">Nothing is deleted on age or low use alone. Any failed or unknown check sends a candidate to <b>manual review</b>. CloudGini never deletes disks, snapshots, images or load balancers itself: it gives you the procedure. The only automated cleanup is releasing an unused non-production IP, which is irreversible and needs typed confirmation.</Notice></div>}
      tabs={[
        { label: "Unattached disks", rules: ["unattached_disk"] },
        { label: "Static IPs", rules: ["unused_ip"] },
        { label: "Snapshots", rules: ["orphaned_snapshot"] },
        { label: "Load balancers", rules: ["unused_lb"] },
        { label: "Abandoned dev", rules: ["abandoned_dev"] },
        { label: "Old images", rules: ["old_image"] },
        { label: "Unowned", rules: ["unowned"] },
      ]} />
  );
}
