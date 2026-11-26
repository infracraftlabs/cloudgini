"""The only remediation actions CloudGini can take. No shell, no arbitrary API calls,
no deletion of production resources. Every action is planned (dry-run) before approval."""
from __future__ import annotations

from typing import Any

from ..providers.base import ActionPlan, ResourceRecord

NON_PRODUCTION = {"dev", "development", "test", "testing", "staging", "sandbox", "demo", "qa"}
IAP_RANGE = "35.235.240.0/20"  # Google's documented range for IAP TCP forwarding
PUBLIC_MEMBERS = {"allUsers", "allAuthenticatedUsers"}

ACTION_TYPES: dict[str, dict[str, Any]] = {
    "stop_vm": {"resource_type": "vm", "reversible": True, "destructive": False,
                "label": "Stop a non-production VM"},
    "resize_vm": {"resource_type": "vm", "reversible": True, "destructive": False,
                  "label": "Resize a non-production VM (same machine family)"},
    "release_ip": {"resource_type": "static_ip", "reversible": False, "destructive": True,
                   "label": "Release an unused static IP address"},
    "restrict_firewall": {"resource_type": "firewall_rule", "reversible": True, "destructive": False,
                          "label": "Restrict a firewall rule's source ranges"},
    "remove_public_access": {"resource_type": "bucket", "reversible": True, "destructive": False,
                             "label": "Remove public access from a bucket"},
}


class ActionBlocked(Exception):
    """The action is not allowed. The message says why, in plain English."""


def check_allowed(action_type: str, resource: ResourceRecord) -> None:
    spec = ACTION_TYPES.get(action_type)
    if spec is None:
        raise ActionBlocked(f"'{action_type}' is not an allowed action type")
    if resource.resource_type != spec["resource_type"]:
        raise ActionBlocked(f"{action_type} only applies to {spec['resource_type']} resources")
    env = (resource.environment or "unknown").lower()
    if env not in NON_PRODUCTION:
        raise ActionBlocked(
            f"blocked: environment is '{env}'. CloudGini only changes resources labelled as non-production "
            f"({', '.join(sorted(NON_PRODUCTION))}); production and unlabelled resources need your normal change process")


def build_plan(action_type: str, r: ResourceRecord, params: dict[str, Any]) -> ActionPlan:
    check_allowed(action_type, r)
    c = r.config
    zone = c.get("zone", r.region or "ZONE")
    if action_type == "stop_vm":
        if c.get("status") != "RUNNING":
            raise ActionBlocked(f"VM is {c.get('status')}, not RUNNING")
        return ActionPlan(
            action_type=action_type, resource_external_id=r.external_id, params={},
            steps=[f"Stop instance {r.name} in {zone} (the boot disk and its data are kept)"],
            before={"status": "RUNNING"}, after={"status": "TERMINATED"},
            preconditions=["status is RUNNING", f"environment is {r.environment}"],
            reversible=True, destructive=False,
            rollback=f"Start it again: gcloud compute instances start {r.name} --zone {zone} --project {r.project}")
    if action_type == "resize_vm":
        target = params.get("machine_type")
        current = c.get("machine_type", "")
        if not target or target.rsplit("-", 1)[0] != current.rsplit("-", 1)[0]:
            raise ActionBlocked("resize must keep the same machine family (e.g. e2-standard-8 to e2-standard-4)")
        return ActionPlan(
            action_type=action_type, resource_external_id=r.external_id, params={"machine_type": target},
            steps=[f"Stop {r.name}", f"Set machine type {current} -> {target}", f"Start {r.name} (only if it was running)"],
            before={"machine_type": current}, after={"machine_type": target},
            preconditions=[f"machine type is {current}", f"environment is {r.environment}", "a short outage is acceptable"],
            reversible=True, destructive=False,
            rollback=(f"Stop the VM, then: gcloud compute instances set-machine-type {r.name} --zone {zone} "
                      f"--machine-type {current} --project {r.project}, then start it"))
    if action_type == "release_ip":
        if c.get("status") != "RESERVED" or c.get("users"):
            raise ActionBlocked("address is in use")
        return ActionPlan(
            action_type=action_type, resource_external_id=r.external_id, params={},
            steps=[f"Release static address {r.name} ({c.get('address')})"],
            before={"status": "RESERVED", "address": c.get("address")}, after={"exists": False},
            preconditions=["status is RESERVED", "no users reference it"],
            reversible=False, destructive=True,
            rollback=("IRREVERSIBLE: once released, this exact IP address cannot be reserved again. "
                      "To recover, reserve a new address and update any DNS records or allow-lists that used the old one."))
    if action_type == "restrict_firewall":
        target = params.get("source_ranges") or [IAP_RANGE]
        return ActionPlan(
            action_type=action_type, resource_external_id=r.external_id, params={"source_ranges": target},
            steps=[f"Update firewall rule {r.name}: source ranges {c.get('source_ranges')} -> {target}"],
            before={"source_ranges": c.get("source_ranges")}, after={"source_ranges": target},
            preconditions=["rule is INGRESS", f"environment is {r.environment}"],
            reversible=True, destructive=False,
            rollback=(f"gcloud compute firewall-rules update {r.name} --project {r.project} "
                      f"--source-ranges {','.join(c.get('source_ranges') or [])}"))
    if action_type == "remove_public_access":
        public = sorted(m for b in c.get("iam_bindings", []) for m in b["members"] if m in PUBLIC_MEMBERS)
        if not public:
            raise ActionBlocked("bucket has no public members")
        roles = sorted({b["role"] for b in c.get("iam_bindings", []) if set(b["members"]) & PUBLIC_MEMBERS})
        return ActionPlan(
            action_type=action_type, resource_external_id=r.external_id, params={},
            steps=[f"Remove {', '.join(public)} from bucket {r.name} ({', '.join(roles)})"],
            before={"public_members": public}, after={"public_members": []},
            preconditions=["bucket is public", f"environment is {r.environment}", "nothing should depend on anonymous access"],
            reversible=True, destructive=False,
            rollback=" ; ".join(f"gcloud storage buckets add-iam-policy-binding gs://{r.name} --member={m} --role={role}"
                                for m in public for role in roles))
    raise ActionBlocked(f"'{action_type}' is not an allowed action type")


def expected_state(plan: ActionPlan, r: ResourceRecord | None) -> tuple[bool, dict[str, Any]]:
    """Compare a fresh read of the resource with the plan's `after`. Used by every provider's verify."""
    if plan.action_type == "release_ip":
        return r is None, {"exists": r is not None}
    if r is None:
        return False, {"exists": False}
    c = r.config
    if plan.action_type == "stop_vm":
        obs = {"status": c.get("status")}
        return obs["status"] in ("TERMINATED", "STOPPED"), obs
    if plan.action_type == "resize_vm":
        obs = {"machine_type": c.get("machine_type")}
        return obs == plan.after, obs
    if plan.action_type == "restrict_firewall":
        obs = {"source_ranges": sorted(c.get("source_ranges") or [])}
        return obs["source_ranges"] == sorted(plan.after["source_ranges"]), obs
    if plan.action_type == "remove_public_access":
        public = sorted(m for b in c.get("iam_bindings", []) for m in b["members"] if m in PUBLIC_MEMBERS)
        return not public, {"public_members": public}
    return False, {}
