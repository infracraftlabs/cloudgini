"""Module C: unused-resource cleanup. Age or low use alone is never enough: every candidate has
dependency, retention, backup and ownership checks, and any failed or unknown check turns it into
'requires manual review'. CloudGini never deletes disks, snapshots, images or load balancers itself;
it gives a procedure. The only automated cleanup is releasing a non-production static IP."""
from __future__ import annotations

from typing import Any

from ..providers.base import ResourceMetrics, ResourceRecord
from .common import Draft, age_days, check, ev, is_prod

BILLABLE = {"vm", "disk", "cloudsql", "bucket", "static_ip", "load_balancer", "snapshot", "image"}


def _owner_check(r: ResourceRecord) -> dict[str, Any]:
    return check("Owner", "pass" if r.owner else "fail",
                 f"owner label: {r.owner}" if r.owner else "no owner label: nobody to confirm with")


def _env_check(r: ResourceRecord) -> dict[str, Any]:
    prod = is_prod(r.environment)
    return check("Environment", "fail" if prod else "pass",
                 f"environment '{r.environment}'" + (": production or unlabelled, manual change only" if prod else ""))


def _retention_check(r: ResourceRecord) -> dict[str, Any]:
    keep = {k: v for k, v in r.labels.items() if k in ("retention", "legal-hold", "keep")}
    return check("Retention", "fail" if keep else "pass",
                 f"retention label present: {keep}" if keep else "no retention or legal-hold label")


def _finish(d: Draft) -> Draft:
    bad = [c for c in d.checks if c["status"] != "pass"]
    if bad:
        d.manual_review_reason = "; ".join(f"{c['name']}: {c['detail']}" for c in bad)
        d.action_type = None
        d.confidence = "low"
    return d


def evaluate(resources: list[ResourceRecord], metrics: dict[str, ResourceMetrics | None], t: dict[str, Any]) -> list[Draft]:
    out: list[Draft] = []
    snapshots = [r for r in resources if r.resource_type == "snapshot"]
    ips = [r for r in resources if r.resource_type == "static_ip"]
    for r in resources:
        c = r.config
        if r.resource_type == "disk" and not c.get("users"):
            # never attached: no detach time, so count from creation
            days = age_days(c.get("last_detach") or (None if c.get("last_attach") else c.get("created")))
            if days is None or days < t["unattached_disk_days"]:
                continue
            backups = [s for s in snapshots if s.config.get("source_disk") == r.name and (age_days(s.config.get("created")) or 999) <= 30]
            d = Draft(kind="cleanup", rule="unattached_disk", resource_external_id=r.external_id, severity="low",
                      title=f"Unattached disk {r.name} ({c['size_gb']} GB {c['disk_type']})",
                      summary=f"Not attached to any VM for {days} days.",
                      evidence=[ev("Attached to", "nothing", "disk.users (inventory)"),
                                ev("Unattached for", f"{days} days", "disk.lastDetachTimestamp (or creationTimestamp)")],
                      checks=[check("Dependencies", "pass", "no VM or instance template uses it"),
                              check("Backup", "pass" if backups else "fail",
                                    f"recent snapshot {backups[0].name}" if backups else "no snapshot in the last 30 days"),
                              _retention_check(r), _owner_check(r), _env_check(r)],
                      current_config={"size_gb": c["size_gb"], "disk_type": c["disk_type"], "users": []},
                      recommended_config={"exists": False}, savings_full=True, confidence="high", risk="medium",
                      impact="Deleting a disk destroys its data. IRREVERSIBLE unless a snapshot exists.",
                      procedure=["Confirm with the owner", "Snapshot it if there is no recent backup",
                                 f"gcloud compute disks delete {r.name} --zone {c.get('zone')} --project {r.project}"])
            out.append(_finish(d))
        elif r.resource_type == "static_ip" and c.get("status") == "RESERVED" and not c.get("users"):
            d = Draft(kind="cleanup", rule="unused_ip", resource_external_id=r.external_id, severity="low",
                      title=f"Unused static IP {r.name} ({c.get('address')})",
                      summary=f"Reserved {age_days(c.get('reserved_at')) or '?'} days ago and not used by any resource.",
                      evidence=[ev("Status", "RESERVED", "address.status"), ev("Users", "none", "address.users")],
                      checks=[check("Dependencies", "pass", "no forwarding rule or VM uses it"),
                              check("DNS", "unknown" if is_prod(r.environment) else "pass",
                                    "check no DNS record or partner allow-list still points at this address"),
                              _owner_check(r), _env_check(r)],
                      current_config={"address": c.get("address"), "status": "RESERVED"},
                      recommended_config={"exists": False}, savings_full=True, confidence="high", risk="low",
                      impact="IRREVERSIBLE: a released address can't be reserved again.",
                      procedure=["Check DNS and allow-lists for the address", "Release it (dry-run, approve with confirmation, execute)"],
                      action_type="release_ip")
            out.append(_finish(d))
        elif r.resource_type == "snapshot" and not c.get("source_disk_exists"):
            days = age_days(c.get("created")) or 0
            if days < t["snapshot_retention_days"]:
                continue
            d = Draft(kind="cleanup", rule="orphaned_snapshot", resource_external_id=r.external_id, severity="low",
                      title=f"Orphaned snapshot {r.name} ({c['size_gb']} GB, {days} days old)",
                      summary=f"Its source disk {c['source_disk']} no longer exists.",
                      evidence=[ev("Source disk", f"{c['source_disk']} (deleted)", "snapshot.sourceDisk"),
                                ev("Age", f"{days} days", "snapshot.creationTimestamp")],
                      checks=[check("Dependencies", "fail" if c.get("used_by_images") else "pass",
                                    f"used by images {c['used_by_images']}" if c.get("used_by_images") else "no image uses it"),
                              check("Schedule", "fail" if c.get("snapshot_schedule") else "pass", "not part of a snapshot schedule"),
                              _retention_check(r), _owner_check(r), _env_check(r)],
                      current_config={"size_gb": c["size_gb"], "created": c["created"]}, recommended_config={"exists": False},
                      savings_full=True, confidence="medium", risk="medium",
                      impact="IRREVERSIBLE: this may be the only copy of the deleted disk's data.",
                      procedure=["Confirm with the owner that the data isn't needed",
                                 f"gcloud compute snapshots delete {r.name} --project {r.project}"])
            out.append(_finish(d))
        elif r.resource_type == "load_balancer" and not c.get("backends"):
            m = metrics.get(r.external_id)
            rpm = m.series["requests_per_min"].p95 if m and "requests_per_min" in m.series else None
            attached_ips = [ip.name for ip in ips if r.name in (ip.config.get("users") or [])]
            d = Draft(kind="cleanup", rule="unused_lb", resource_external_id=r.external_id, severity="low",
                      title=f"Unused load balancer {r.name}",
                      summary="No backends" + (f" and {rpm:g} requests/min (p95) over {m.observation_days} days." if rpm is not None else "."),
                      evidence=[ev("Backends", "none", "backend services")] + (
                          [ev("Requests", f"{rpm:g}/min p95", f"{m.series['requests_per_min'].source}, last {m.observation_days} days")] if rpm is not None else []),
                      checks=[check("Traffic", "pass" if rpm == 0 else "unknown",
                                    "no requests in the window" if rpm == 0 else "no request metrics"),
                              check("Dependencies", "pass", f"static IP {', '.join(attached_ips)} is attached: release it after removal"
                                    if attached_ips else "no other resources reference it"),
                              _owner_check(r), _env_check(r)],
                      observation_days=m.observation_days if m else None,
                      current_config={"forwarding_rules": c.get("forwarding_rules"), "backends": []},
                      recommended_config={"exists": False}, savings_full=True, confidence="medium", risk="low",
                      impact="Removes the forwarding rule, proxy and URL map. Re-creating needs the config (keep it in Terraform).",
                      procedure=["Check DNS no longer points at it", "Delete forwarding rule, target proxy and URL map",
                                 "Then review the attached static IP"])
            out.append(_finish(d))
        elif r.resource_type == "vm" and c.get("status") == "TERMINATED" and not is_prod(r.environment):
            days = age_days(c.get("last_stop"))
            if days is None or days < t["abandoned_days"]:
                continue
            d = Draft(kind="cleanup", rule="abandoned_dev", resource_external_id=r.external_id, severity="low",
                      title=f"Possibly abandoned dev VM {r.name}", summary=f"Stopped for {days} days in '{r.environment}'.",
                      evidence=[ev("Status", "TERMINATED", "instance.status"), ev("Stopped", f"{days} days ago", "instance.lastStopTimestamp")],
                      checks=[check("Activity", "unknown", "being stopped doesn't prove nobody needs it"), _owner_check(r),
                              _env_check(r)],
                      current_config={"status": "TERMINATED"}, recommended_config={"exists": False},
                      confidence="low", risk="medium",
                      impact="A stopped VM costs nothing for compute, but its disks and any reserved IP still cost money.",
                      procedure=["Find the owner (audit logs show who created it)", "Snapshot its disks",
                                 "Delete the VM and disks through your normal process"])
            out.append(_finish(d))
        elif r.resource_type == "image":
            days = age_days(c.get("created")) or 0
            if days < t["image_age_days"] or c.get("used_by") or c.get("deprecated"):
                continue
            d = Draft(kind="cleanup", rule="old_image", resource_external_id=r.external_id, severity="info",
                      title=f"Old unused image {r.name} ({days} days)", summary="Not used by any instance template or VM.",
                      evidence=[ev("Created", f"{days} days ago", "image.creationTimestamp"), ev("Used by", "nothing", "instance templates")],
                      checks=[check("Dependencies", "pass", "no instance template references it"), _retention_check(r),
                              _owner_check(r), _env_check(r)],
                      current_config={"family": c.get("family"), "size_gb": c.get("size_gb")}, recommended_config={"deprecated": "DEPRECATED"},
                      savings_full=True, confidence="medium", risk="low",
                      impact="Deprecate first so anyone still using it gets a warning; delete after 30 days.",
                      procedure=[f"gcloud compute images deprecate {r.name} --state DEPRECATED --project {r.project}",
                                 "After 30 days without complaints, delete it"])
            out.append(_finish(d))
        if r.resource_type in BILLABLE and not r.owner:
            out.append(Draft(kind="cleanup", rule="unowned", resource_external_id=r.external_id, severity="info",
                             title=f"Resource without owner: {r.name}", summary="No owner label, so nobody can confirm whether it's needed.",
                             evidence=[ev("Labels", r.labels or "none", "resource labels")],
                             checks=[_owner_check(r)], confidence="high", risk="low",
                             impact="Unowned resources are the hardest to clean up safely.",
                             procedure=["Find the creator in Cloud Audit Logs", "Add an `owner` label"],
                             manual_review_reason="no owner label: find and label an owner before any cleanup"))
    return out
