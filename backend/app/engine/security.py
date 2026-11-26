"""Module D: ten rules-based security checks. Findings describe configuration facts and their
likely impact; they are not a compliance assessment."""
from __future__ import annotations

from typing import Any

from ..providers.base import ResourceRecord
from .actions import IAP_RANGE, PUBLIC_MEMBERS
from .common import Draft, age_days, ev, is_prod

ANYWHERE = {"0.0.0.0/0", "::/0"}
PRIMITIVE = {"roles/owner", "roles/editor"}
SENSITIVE_VALUES = {"sensitive", "confidential", "restricted", "pii"}

CHECKS = {
    "public_bucket": "Public storage buckets",
    "permissive_iam": "Overly permissive IAM",
    "open_ssh_rdp": "SSH or RDP open to the internet",
    "public_database": "Publicly reachable databases",
    "encryption": "Encryption settings",
    "audit_logging": "Data access audit logging",
    "stale_sa_keys": "Old service account keys",
    "sa_excessive_permissions": "Service accounts with broad roles",
    "unowned_sensitive": "Sensitive resources without an owner",
    "firewall_misconfiguration": "Firewall misconfiguration",
}


def _sensitive(r: ResourceRecord) -> bool:
    return r.labels.get("data-classification", "").lower() in SENSITIVE_VALUES


def _ports(rule: dict[str, Any]) -> set[str]:
    out = set()
    for a in rule.get("allowed", []):
        if a.get("protocol") == "all" or (a.get("protocol") == "tcp" and not a.get("ports")):
            out.add("all")
        for p in a.get("ports", []) or []:
            out.add(str(p))
    return out


def _port_covers(ports: set[str], target: int) -> bool:
    for p in ports:
        if p == "all":
            return True
        if "-" in p:
            lo, hi = p.split("-")
            if int(lo) <= target <= int(hi):
                return True
        elif p.isdigit() and int(p) == target:
            return True
    return False


def _f(rule: str, r: ResourceRecord, **kw: Any) -> Draft:
    return Draft(kind="security", rule=rule, resource_external_id=r.external_id, **kw)


def evaluate(resources: list[ResourceRecord], t: dict[str, Any]) -> list[Draft]:
    out: list[Draft] = []
    for r in resources:
        c = r.config
        prod = is_prod(r.environment)
        if r.resource_type == "bucket":
            public = sorted({m for b in c.get("iam_bindings", []) for m in b["members"] if m in PUBLIC_MEMBERS})
            if public:
                out.append(_f("public_bucket", r, severity="critical" if _sensitive(r) else "high",
                              title=f"Bucket {r.name} is public",
                              summary=f"{', '.join(public)} can read objects in this bucket.",
                              evidence=[ev("IAM members", ", ".join(public), "bucket IAM policy")] +
                                       ([ev("Data classification", r.labels["data-classification"], "labels")] if _sensitive(r) else []),
                              current_config={"public_members": public}, recommended_config={"public_members": []},
                              impact="Anyone who finds the bucket name can download its objects.",
                              procedure=["Check nothing needs anonymous access (e.g. a website: use a load balancer + signed URLs instead)",
                                         "Remove the public members", "Turn on Public Access Prevention for the bucket"],
                              risk="medium", confidence="high",
                              action_type=None if prod else "remove_public_access",
                              manual_review_reason="production bucket: change through your normal process" if prod else None))
            if _sensitive(r) and c.get("encryption") != "cmek":
                out.append(_f("encryption", r, severity="low", title=f"Sensitive bucket {r.name} uses Google-managed keys",
                              summary="Data is encrypted at rest with Google-managed keys; no customer-managed key (CMEK) is set.",
                              evidence=[ev("Encryption", c.get("encryption"), "bucket.encryption"),
                                        ev("Data classification", r.labels["data-classification"], "labels")],
                              impact="Not a gap in itself. CMEK adds control over key rotation and revocation if your policy requires it.",
                              procedure=["Decide whether your data policy requires CMEK", "If yes, set a default KMS key on the bucket"],
                              risk="low", confidence="high"))
        if r.resource_type == "iam_policy":
            # Flag: any role for public members, Owner for individual users, Editor for anyone.
            risky = [(b["role"], m) for b in c.get("bindings", []) for m in b["members"]
                     if m in PUBLIC_MEMBERS or b["role"] == "roles/editor"
                     or (b["role"] == "roles/owner" and m.startswith("user:"))]
            if risky:
                out.append(_f("permissive_iam", r, severity="high", title=f"Broad primitive roles in project {r.project}",
                              summary="; ".join(f"{m} has {role}" for role, m in risky),
                              evidence=[ev("Binding", f"{role} -> {m}", "project IAM policy") for role, m in risky],
                              current_config={"bindings": [f"{role}: {m}" for role, m in risky]},
                              recommended_config={"bindings": "predefined roles scoped to what each member needs"},
                              impact="Owner and Editor can change almost everything in the project, including IAM.",
                              procedure=["Use IAM Recommender's role suggestions as a starting point",
                                         "Grant predefined roles to groups instead of users", "Remove the primitive role"],
                              risk="medium", confidence="high",
                              manual_review_reason="IAM changes can lock people out; CloudGini doesn't change IAM bindings"))
            logs = {lt for a in c.get("audit_configs", []) if a.get("service") == "allServices" for lt in a.get("log_types", [])}
            if not {"DATA_READ", "DATA_WRITE"} <= logs:
                out.append(_f("audit_logging", r, severity="medium", title=f"Data access audit logs off in project {r.project}",
                              summary="Admin activity is always logged, but data reads and writes are not.",
                              evidence=[ev("Audit config (allServices)", sorted(logs) or "none", "project IAM policy auditConfigs")],
                              impact="You couldn't tell who read or changed data during an incident.",
                              procedure=["Enable DATA_READ and DATA_WRITE for allServices (or for the services holding data)",
                                         "Check the extra log volume and its cost first"],
                              risk="low", confidence="high",
                              manual_review_reason="turning on data access logs adds log volume and cost: decide per project"))
        if r.resource_type == "firewall_rule" and c.get("direction") == "INGRESS" and not c.get("disabled"):
            if not set(c.get("source_ranges", [])) & ANYWHERE:
                continue
            ports = _ports(c)
            open_admin = [p for p, n in ((22, "SSH"), (3389, "RDP")) if _port_covers(ports, p)]
            action = None if prod else "restrict_firewall"
            reason = "production firewall: change through your normal process" if prod else None
            common = dict(current_config={"source_ranges": c["source_ranges"], "allowed": c.get("allowed")},
                          recommended_config={"source_ranges": [IAP_RANGE]}, action_type=action,
                          action_params={"source_ranges": [IAP_RANGE]}, manual_review_reason=reason, confidence="high")
            ev_rule = [ev("Source ranges", ", ".join(c["source_ranges"]), "firewall rule"),
                       ev("Allowed", ", ".join(sorted(ports)), "firewall rule"),
                       ev("Targets", ", ".join(c.get("target_tags") or []) or "all instances in the network", "firewall rule")]
            if "all" in ports or not c.get("target_tags"):
                out.append(_f("firewall_misconfiguration", r, severity="high",
                              title=f"Firewall rule {r.name} allows all traffic from the internet" if "all" in ports
                              else f"Firewall rule {r.name} applies to every instance",
                              summary="Ingress from 0.0.0.0/0 " + ("on all protocols and ports" if "all" in ports else "with no target tags"),
                              evidence=ev_rule, impact="Every service listening on any VM in the network is reachable from the internet.",
                              procedure=["Find what actually needs inbound access", "Narrow ports, sources and target tags",
                                         f"For admin access use IAP TCP forwarding ({IAP_RANGE})"],
                              risk="medium", **common))
            elif open_admin:
                names = " and ".join("SSH" if p == 22 else "RDP" for p in open_admin)
                out.append(_f("open_ssh_rdp", r, severity="high", title=f"{names} open to the internet ({r.name})",
                              summary=f"Port(s) {', '.join(map(str, open_admin))} allowed from 0.0.0.0/0.",
                              evidence=ev_rule, impact="Admin ports exposed to the internet are scanned and brute-forced constantly.",
                              procedure=[f"Use IAP TCP forwarding: restrict source to {IAP_RANGE}",
                                         "Grant roles/iap.tunnelResourceAccessor to the people who need it"],
                              risk="low", **common))
        if r.resource_type == "cloudsql":
            nets = c.get("authorized_networks") or []
            if c.get("public_ip") and set(nets) & ANYWHERE:
                out.append(_f("public_database", r, severity="critical", title=f"Cloud SQL {r.name} accepts connections from anywhere",
                              summary="Public IP with an authorised network of 0.0.0.0/0.",
                              evidence=[ev("Public IP", "enabled", "settings.ipConfiguration.ipv4Enabled"),
                                        ev("Authorised networks", ", ".join(nets), "settings.ipConfiguration.authorizedNetworks")],
                              impact="Only the database password stands between the internet and your data.",
                              procedure=["Use the Cloud SQL Auth Proxy or private IP", "Remove 0.0.0.0/0 from authorised networks",
                                         "Disable the public IP once clients have moved"],
                              risk="medium", confidence="high",
                              manual_review_reason="clients must move to private IP or the Auth Proxy first"))
            if not c.get("ssl_required"):
                out.append(_f("encryption", r, severity="medium", title=f"Cloud SQL {r.name} allows unencrypted connections",
                              summary="SSL/TLS is not required for client connections.",
                              evidence=[ev("requireSsl / sslMode", "not enforced", "settings.ipConfiguration")],
                              impact="Credentials and data could cross the network in clear text.",
                              procedure=["Set ssl mode to ENCRYPTED_ONLY", "Check every client supports TLS first"],
                              risk="medium", confidence="high",
                              manual_review_reason="clients without TLS would lose access"))
        if r.resource_type == "service_account":
            old = [k for k in c.get("keys", []) if k.get("type") == "USER_MANAGED" and (age_days(k.get("created")) or 0) > t["sa_key_max_age_days"]]
            if old:
                out.append(_f("stale_sa_keys", r, severity="high" if set(c.get("roles", [])) & PRIMITIVE else "medium",
                              title=f"Old key on service account {r.name}",
                              summary=", ".join(f"key {k['id']} is {age_days(k['created'])} days old" for k in old),
                              evidence=[ev("Key", f"{k['id']} created {age_days(k['created'])} days ago", "service account keys") for k in old],
                              impact="Long-lived keys leak through laptops, CI logs and repos, and work from anywhere.",
                              procedure=["Replace the key with Workload Identity Federation (e.g. for CI)",
                                         "If a key is unavoidable, rotate it and delete the old one"],
                              risk="medium", confidence="high",
                              manual_review_reason="deleting a key breaks whatever uses it: find the user first"))
            broad = sorted(set(c.get("roles", [])) & PRIMITIVE)
            if broad:
                out.append(_f("sa_excessive_permissions", r, severity="high", title=f"Service account {r.name} has {', '.join(broad)}",
                              summary="A workload identity with a primitive role can change most of the project.",
                              evidence=[ev("Roles", ", ".join(c.get("roles", [])), "project IAM policy")],
                              impact="If the workload or its key is compromised, so is the project.",
                              procedure=["List what the account actually calls (Policy Analyzer / IAM Recommender)",
                                         "Grant those predefined roles", "Remove the primitive role"],
                              risk="medium", confidence="high",
                              manual_review_reason="IAM changes can break deployments; CloudGini doesn't change IAM bindings"))
        if _sensitive(r) and not r.owner:
            out.append(_f("unowned_sensitive", r, severity="medium", title=f"Sensitive resource {r.name} has no owner",
                          summary=f"Labelled data-classification={r.labels['data-classification']} but no owner label.",
                          evidence=[ev("Labels", r.labels, "resource labels")],
                          impact="Nobody is accountable for who can access this data.",
                          procedure=["Find the creator in Cloud Audit Logs", "Add an owner label", "Review access with that owner"],
                          risk="low", confidence="high",
                          manual_review_reason="needs a person to take ownership"))
    return out


def still_failing(rule: str, resource: ResourceRecord | None, t: dict[str, Any]) -> bool:
    """Used for verification: is the finding still present on a fresh read of the resource?"""
    if resource is None:
        return False
    return any(d.rule == rule for d in evaluate([resource], t))
