"""Simulated provider: a small synthetic GCP-like estate with planted issues.

All names are invented (example.com, demo-shop-*). Prices come from a SYNTHETIC price table
that only exists so the demo can show savings maths; it is not real cloud pricing and every
figure it produces is labelled simulated. State lives in memory and resets with reset().
"""
from __future__ import annotations

import copy
import random
from datetime import date, datetime, timedelta, timezone
from typing import Any

from ..engine.actions import build_plan, expected_state
from .base import (ActionPlan, ActionResult, CloudProvider, CostData, CostEstimate, CostRecord, MetricSeries,
                   ProviderFinding, ResourceMetrics, ResourceRecord, Verification)

DS = "simulated"
SYNTHETIC_PRICES = {  # USD per month. Synthetic, for the demo only.
    "vcpu": 24.0, "mem_gb": 3.2, "pd-ssd": 0.17, "pd-balanced": 0.10, "pd-standard": 0.04,
    "STANDARD": 0.020, "NEARLINE": 0.010, "COLDLINE": 0.004, "ARCHIVE": 0.0012,
    "static_ip": 7.3, "load_balancer": 18.0, "sql_vcpu": 30.0, "sql_mem_gb": 5.0, "snapshot_gb": 0.026, "image_gb": 0.05,
}
MACHINES = {  # family-size: (vcpus, memory GB)
    "e2-small": (2, 2), "e2-standard-2": (2, 8), "e2-standard-4": (4, 16), "e2-standard-8": (8, 32),
    "n2-standard-4": (4, 16), "n2-standard-8": (8, 32), "n2-standard-16": (16, 64), "n2-highmem-8": (8, 64),
}
SQL_TIERS = {"db-custom-2-8192": (2, 8), "db-custom-4-16384": (4, 16), "db-custom-8-32768": (8, 32)}


def _iso(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).replace(microsecond=0).isoformat()


def _r(rtype: str, project: str, name: str, env: str | None, owner: str | None, config: dict[str, Any],
       region: str = "europe-west1", extra_labels: dict[str, str] | None = None) -> ResourceRecord:
    labels = dict(extra_labels or {})
    if env:
        labels["env"] = env
    if owner:
        labels["owner"] = owner
    return ResourceRecord(external_id=f"//sim/{project}/{rtype}/{name}", name=name, resource_type=rtype,
                          project=project, region=region, environment=env or "unknown", owner=owner,
                          labels=labels, config=config, data_source=DS)


def _vm(project, name, env, owner, mtype, status="RUNNING", **extra):
    v, m = MACHINES[mtype]
    return _r("vm", project, name, env, owner, {"machine_type": mtype, "vcpus": v, "memory_gb": m, "status": status,
                                                "zone": "europe-west1-b", **extra.pop("config", {})}, **extra)


def build_world() -> tuple[list[ResourceRecord], dict[str, ResourceMetrics | None]]:
    R: list[ResourceRecord] = []
    M: dict[str, ResourceMetrics | None] = {}

    def metrics(res: ResourceRecord, days: int, **series: tuple[float, str, str]):
        M[res.external_id] = ResourceMetrics(observation_days=days, data_source=DS, series={
            k: MetricSeries(p95=v[0], avg=round(v[0] * 0.6, 1), max=round(v[0] * 1.3, 1), unit=v[1], source=v[2])
            for k, v in series.items()})

    cpu = "compute.googleapis.com/instance/cpu/utilization"
    mem = "agent.googleapis.com/memory/percent_used"
    # --- VMs
    a = _vm("demo-shop-dev", "api-dev-1", "dev", "team-shop", "e2-standard-8"); R.append(a)
    metrics(a, 30, cpu_p95=(12.0, "%", cpu), mem_p95=(28.0, "%", mem))
    b = _vm("demo-shop-dev", "batch-dev-2", "dev", "team-shop", "e2-standard-4"); R.append(b)
    metrics(b, 30, cpu_p95=(2.1, "%", cpu), mem_p95=(9.0, "%", mem))
    c = _vm("demo-shop-staging", "web-stg-1", "staging", "team-shop", "n2-standard-4"); R.append(c)
    metrics(c, 30, cpu_p95=(58.0, "%", cpu), mem_p95=(61.0, "%", mem))
    d = _vm("demo-shop-prod", "web-prod-1", "prod", "team-shop", "n2-standard-16"); R.append(d)
    metrics(d, 30, cpu_p95=(17.0, "%", cpu), mem_p95=(33.0, "%", mem))
    e = _vm("demo-data-dev", "notebook-dev-1", "dev", "team-data", "n2-highmem-8"); R.append(e)
    metrics(e, 30, cpu_p95=(6.0, "%", cpu))  # no memory agent: memory metric missing
    f = _vm("demo-data-dev", "etl-dev-3", "dev", "team-data", "e2-standard-8"); R.append(f)
    metrics(f, 5, cpu_p95=(4.0, "%", cpu), mem_p95=(12.0, "%", mem))  # too new to judge
    g = _vm("demo-shop-dev", "legacy-dev-vm", "dev", None, "e2-standard-2", status="TERMINATED",
            config={"last_stop": _iso(64)}); R.append(g)
    M[g.external_id] = None
    h = _vm("demo-shop-prod", "bastion-prod", "prod", "team-platform", "e2-small", config={"tags": ["ssh"]}); R.append(h)
    metrics(h, 30, cpu_p95=(3.0, "%", cpu), mem_p95=(20.0, "%", mem))
    # --- Disks
    iops = "compute.googleapis.com/instance/disk/read_ops_count+write_ops_count"
    R.append(_r("disk", "demo-shop-dev", "disk-old-data", "dev", "team-shop", {
        "size_gb": 500, "disk_type": "pd-ssd", "users": [], "last_detach": _iso(45), "zone": "europe-west1-b"}))
    R.append(_r("disk", "demo-shop-staging", "disk-tmp-restore", "staging", "team-shop", {
        "size_gb": 200, "disk_type": "pd-standard", "users": [], "last_detach": _iso(10), "zone": "europe-west1-b"}))
    R.append(_r("disk", "demo-data-dev", "disk-ml-scratch", "dev", None, {
        "size_gb": 1000, "disk_type": "pd-ssd", "users": [], "last_detach": _iso(90), "zone": "europe-west1-b"}))
    pd = _r("disk", "demo-shop-prod", "web-prod-1-data", "prod", "team-shop", {
        "size_gb": 2000, "disk_type": "pd-ssd", "users": ["web-prod-1"], "zone": "europe-west1-b"}); R.append(pd)
    metrics(pd, 30, iops_p95=(140.0, "ops/s", iops))
    # --- Cloud SQL
    sqlm = "cloudsql.googleapis.com/database/cpu/utilization"
    sqlmem = "cloudsql.googleapis.com/database/memory/utilization"
    db1 = _r("cloudsql", "demo-shop-prod", "orders-db", "prod", "team-shop", {
        "tier": "db-custom-8-32768", "vcpus": 8, "memory_gb": 32, "public_ip": False, "authorized_networks": [],
        "ssl_required": True, "backups_enabled": True, "database_version": "POSTGRES_16"}); R.append(db1)
    metrics(db1, 30, cpu_p95=(14.0, "%", sqlm), mem_p95=(38.0, "%", sqlmem))
    db2 = _r("cloudsql", "demo-shop-dev", "reporting-db-dev", "dev", "team-shop", {
        "tier": "db-custom-2-8192", "vcpus": 2, "memory_gb": 8, "public_ip": True,
        "authorized_networks": ["0.0.0.0/0"], "ssl_required": False, "backups_enabled": True,
        "database_version": "POSTGRES_16"}); R.append(db2)
    metrics(db2, 30, cpu_p95=(45.0, "%", sqlm), mem_p95=(55.0, "%", sqlmem))
    # --- Load balancers
    lbm = "loadbalancing.googleapis.com/https/request_count"
    lb1 = _r("load_balancer", "demo-shop-staging", "lb-old-campaign", "staging", "team-marketing", {
        "scheme": "EXTERNAL_MANAGED", "forwarding_rules": 1, "backends": [], "url_map": "old-campaign"}, region="global")
    R.append(lb1); metrics(lb1, 30, requests_per_min=(0.0, "req/min", lbm))
    lb2 = _r("load_balancer", "demo-shop-dev", "lb-dev-api", "dev", "team-shop", {
        "scheme": "EXTERNAL_MANAGED", "forwarding_rules": 1, "backends": ["api-dev-1"], "url_map": "dev-api"}, region="global")
    R.append(lb2); metrics(lb2, 30, requests_per_min=(42.0, "req/min", lbm))
    lb3 = _r("load_balancer", "demo-shop-staging", "lb-internal-tools", "staging", "team-platform", {
        "scheme": "EXTERNAL_MANAGED", "forwarding_rules": 1, "backends": ["tools-stg"], "url_map": "internal-tools"},
        region="global")
    R.append(lb3); metrics(lb3, 30, requests_per_min=(0.4, "req/min", lbm))
    # --- GKE workloads
    kcpu = "kubernetes.io/container/cpu/core_usage_time"
    kmem = "kubernetes.io/container/memory/used_bytes"
    w1 = _r("gke_workload", "demo-shop-prod", "checkout-api", "prod", "team-shop", {
        "cluster": "prod-gke", "namespace": "checkout", "replicas": 6, "cpu_request_m": 2000, "mem_request_mi": 4096})
    R.append(w1); metrics(w1, 30, cpu_usage_m=(240.0, "millicores", kcpu), mem_usage_mi=(900.0, "MiB", kmem))
    w2 = _r("gke_workload", "demo-shop-dev", "search-indexer", "dev", "team-shop", {
        "cluster": "dev-gke", "namespace": "search", "replicas": 2, "cpu_request_m": 4000, "mem_request_mi": 8192})
    R.append(w2); metrics(w2, 30, cpu_usage_m=(3500.0, "millicores", kcpu), mem_usage_mi=(7000.0, "MiB", kmem))
    # --- Buckets
    reads = "storage.googleapis.com/api/request_count (read methods)"
    bk1 = _r("bucket", "demo-shop-dev", "demo-shop-dev-public-assets-test", "dev", "team-shop", {
        "storage_class": "STANDARD", "size_gb": 12, "uniform_access": True, "encryption": "google-managed",
        "iam_bindings": [{"role": "roles/storage.objectViewer", "members": ["allUsers"]}]}); R.append(bk1)
    metrics(bk1, 30, reads_per_day=(120.0, "requests/day", reads))
    bk2 = _r("bucket", "demo-data-dev", "demo-data-dev-exports", "dev", None, {
        "storage_class": "STANDARD", "size_gb": 80, "uniform_access": True, "encryption": "google-managed",
        "iam_bindings": [{"role": "roles/storage.objectViewer", "members": ["allAuthenticatedUsers"]}]},
        extra_labels={"data-classification": "sensitive"}); R.append(bk2)
    metrics(bk2, 30, reads_per_day=(3.0, "requests/day", reads))
    bk3 = _r("bucket", "demo-shop-prod", "demo-shop-prod-logs-archive", "prod", "team-platform", {
        "storage_class": "STANDARD", "size_gb": 4000, "uniform_access": True, "encryption": "google-managed",
        "iam_bindings": []}); R.append(bk3)
    metrics(bk3, 90, reads_per_day=(0.0, "requests/day", reads))
    bk4 = _r("bucket", "demo-shop-prod", "demo-shop-prod-media", "prod", "team-shop", {
        "storage_class": "STANDARD", "size_gb": 600, "uniform_access": True, "encryption": "google-managed",
        "iam_bindings": []}); R.append(bk4)
    metrics(bk4, 90, reads_per_day=(250000.0, "requests/day", reads))
    # --- Static IPs
    R.append(_r("static_ip", "demo-shop-dev", "ip-dev-unused", "dev", "team-shop", {
        "address": "203.0.113.10", "status": "RESERVED", "address_type": "EXTERNAL", "users": [], "reserved_at": _iso(120)}))
    R.append(_r("static_ip", "demo-shop-prod", "ip-prod-spare", "prod", "team-platform", {
        "address": "203.0.113.20", "status": "RESERVED", "address_type": "EXTERNAL", "users": [], "reserved_at": _iso(200)}))
    R.append(_r("static_ip", "demo-shop-staging", "ip-stg-lb", "staging", "team-shop", {
        "address": "203.0.113.30", "status": "IN_USE", "address_type": "EXTERNAL", "users": ["lb-old-campaign"]}))
    # --- Snapshots and images
    R.append(_r("snapshot", "demo-shop-dev", "snap-old-2025", "dev", "team-shop", {
        "source_disk": "disk-deleted-2025", "source_disk_exists": False, "created": _iso(400), "size_gb": 300,
        "used_by_images": [], "snapshot_schedule": None}))
    R.append(_r("snapshot", "demo-data-dev", "snap-ml-baseline", "dev", "team-data", {
        "source_disk": "ml-baseline-disk", "source_disk_exists": False, "created": _iso(200), "size_gb": 250,
        "used_by_images": [], "snapshot_schedule": None}, extra_labels={"retention": "keep-until-2027"}))
    R.append(_r("snapshot", "demo-shop-dev", "snap-disk-old-data", "dev", "team-shop", {
        "source_disk": "disk-old-data", "source_disk_exists": True, "created": _iso(3), "size_gb": 120,
        "used_by_images": [], "snapshot_schedule": None}))
    R.append(_r("image", "demo-shop-dev", "img-base-2024", "dev", "team-shop", {
        "created": _iso(500), "family": "base", "deprecated": None, "used_by": [], "size_gb": 20}))
    R.append(_r("image", "demo-shop-prod", "img-web-golden", "prod", "team-shop", {
        "created": _iso(240), "family": "web", "deprecated": None, "used_by": ["instance-template/web-prod"], "size_gb": 20}))
    # --- Firewall rules
    R.append(_r("firewall_rule", "demo-shop-prod", "allow-ssh-all", "prod", "team-platform", {
        "direction": "INGRESS", "source_ranges": ["0.0.0.0/0"], "allowed": [{"protocol": "tcp", "ports": ["22"]}],
        "target_tags": ["ssh"], "disabled": False, "network": "default"}, region="global"))
    R.append(_r("firewall_rule", "demo-shop-dev", "allow-rdp-dev", "dev", "team-shop", {
        "direction": "INGRESS", "source_ranges": ["0.0.0.0/0"], "allowed": [{"protocol": "tcp", "ports": ["3389"]}],
        "target_tags": ["windows"], "disabled": False, "network": "default"}, region="global"))
    R.append(_r("firewall_rule", "demo-shop-dev", "allow-all-dev-legacy", "dev", "team-shop", {
        "direction": "INGRESS", "source_ranges": ["0.0.0.0/0"], "allowed": [{"protocol": "all"}],
        "target_tags": [], "disabled": False, "network": "default"}, region="global",
        extra_labels={"managed-by": "legacy-script"}))  # the simulation re-applies this rule: verification fails
    R.append(_r("firewall_rule", "demo-shop-staging", "allow-health-checks", "staging", "team-shop", {
        "direction": "INGRESS", "source_ranges": ["130.211.0.0/22", "35.191.0.0/16"],
        "allowed": [{"protocol": "tcp", "ports": ["80"]}], "target_tags": ["web"], "disabled": False, "network": "default"},
        region="global"))
    # --- IAM policies (one per project) and service accounts
    R.append(_r("iam_policy", "demo-shop-dev", "demo-shop-dev", "dev", "team-platform", {
        "bindings": [{"role": "roles/owner", "members": ["user:dev-lead@example.com"]},
                     {"role": "roles/editor", "members": ["group:contractors@example.com"]},
                     {"role": "roles/viewer", "members": ["group:shop-team@example.com"]}],
        "audit_configs": []}, region="global"))
    R.append(_r("iam_policy", "demo-shop-prod", "demo-shop-prod", "prod", "team-platform", {
        "bindings": [{"role": "roles/owner", "members": ["group:platform-admins@example.com"]},
                     {"role": "roles/viewer", "members": ["group:shop-team@example.com"]}],
        "audit_configs": [{"service": "allServices", "log_types": ["ADMIN_READ", "DATA_READ", "DATA_WRITE"]}]}, region="global"))
    R.append(_r("iam_policy", "demo-data-dev", "demo-data-dev", "dev", "team-data", {
        "bindings": [{"role": "roles/owner", "members": ["group:data-admins@example.com"]}],
        "audit_configs": []}, region="global"))
    R.append(_r("service_account", "demo-shop-dev", "ci-deployer@demo-shop-dev.iam.gserviceaccount.com", "dev",
                "team-platform", {"roles": ["roles/editor"], "disabled": False,
                                  "keys": [{"id": "k-0001", "type": "USER_MANAGED", "created": _iso(400)}]}, region="global"))
    R.append(_r("service_account", "demo-shop-prod", "app-runtime@demo-shop-prod.iam.gserviceaccount.com", "prod",
                "team-shop", {"roles": ["roles/cloudsql.client", "roles/storage.objectViewer"], "disabled": False,
                              "keys": []}, region="global"))
    R.append(_r("service_account", "demo-data-dev", "etl-runner@demo-data-dev.iam.gserviceaccount.com", "dev",
                "team-data", {"roles": ["roles/owner"], "disabled": False,
                              "keys": [{"id": "k-0002", "type": "USER_MANAGED", "created": _iso(30)}]}, region="global"))
    return R, M


def synthetic_monthly_cost(r: ResourceRecord) -> float | None:
    p, c = SYNTHETIC_PRICES, r.config
    t = r.resource_type
    if t == "vm":
        return 0.0 if c["status"] != "RUNNING" else round(c["vcpus"] * p["vcpu"] + c["memory_gb"] * p["mem_gb"], 2)
    if t == "disk":
        return round(c["size_gb"] * p[c["disk_type"]], 2)
    if t == "cloudsql":
        return round(c["vcpus"] * p["sql_vcpu"] + c["memory_gb"] * p["sql_mem_gb"], 2)
    if t == "load_balancer":
        return p["load_balancer"]
    if t == "bucket":
        return round(c["size_gb"] * p[c["storage_class"]], 2)
    if t == "static_ip":
        return p["static_ip"] if c["status"] == "RESERVED" else 0.0
    if t == "snapshot":
        return round(c["size_gb"] * p["snapshot_gb"], 2)
    if t == "image":
        return round(c["size_gb"] * p["image_gb"], 2)
    return None  # GKE workloads, firewall rules, IAM: no direct line item


SERVICE = {"vm": "Compute Engine", "disk": "Compute Engine", "static_ip": "Compute Engine", "snapshot": "Compute Engine",
           "image": "Compute Engine", "load_balancer": "Networking", "cloudsql": "Cloud SQL", "bucket": "Cloud Storage"}


class SimulatedProvider(CloudProvider):
    name = "simulated"
    data_source = DS

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        resources, self._metrics = build_world()
        self._world = {r.external_id: r for r in resources}

    # Inventory
    def list_resources(self) -> list[ResourceRecord]:
        return [copy.deepcopy(r) for r in self._world.values()]

    def get_resource(self, external_id: str) -> ResourceRecord | None:
        r = self._world.get(external_id)
        return copy.deepcopy(r) if r else None

    def get_resource_metrics(self, resource: ResourceRecord) -> ResourceMetrics | None:
        return self._metrics.get(resource.external_id)

    # Cost
    def get_cost_data(self, start: date, end: date) -> CostData:
        rng = random.Random(42)
        records: list[CostRecord] = []
        days = (end - start).days + 1
        for r in self._world.values():
            monthly = synthetic_monthly_cost(r)
            if not monthly:
                continue
            for i in range(days):
                day = start + timedelta(days=i)
                drift = 1.0 + 0.15 * (i / max(days, 1))  # slow growth, so the trend chart has a shape
                records.append(CostRecord(day=day, service=SERVICE.get(r.resource_type, "Other"), project=r.project,
                                          environment=r.environment, resource_external_id=r.external_id,
                                          cost=round(monthly / 30 * drift * rng.uniform(0.9, 1.1), 4)))
        return CostData(records=records, basis="simulated_billing", data_source=DS,
                        note="Synthetic billing generated from a synthetic price table; not real cloud prices.")

    def estimate_resource_cost(self, resource: ResourceRecord, config: dict[str, Any], current_monthly: float) -> CostEstimate | None:
        merged = resource.model_copy(update={"config": {**resource.config, **config}})
        if resource.resource_type == "vm" and "machine_type" in config:
            v, m = MACHINES[config["machine_type"]]
            merged.config.update(vcpus=v, memory_gb=m)
        if resource.resource_type == "cloudsql" and "tier" in config:
            v, m = SQL_TIERS[config["tier"]]
            merged.config.update(vcpus=v, memory_gb=m)
        now_list, new_list = synthetic_monthly_cost(resource), synthetic_monthly_cost(merged)
        if not now_list or new_list is None:
            return None
        return CostEstimate(monthly=round(current_monthly * new_list / now_list, 2),
                            method=(f"billed cost x ({new_list:g} / {now_list:g}) from a synthetic price table "
                                    "(simulated provider; not real cloud prices)"))

    # Security
    def get_security_findings(self) -> list[ProviderFinding]:
        return []  # the simulated estate has no Security Command Center; CloudGini's own rules still run

    # Remediation
    def plan_action(self, action_type: str, resource: ResourceRecord, params: dict[str, Any]) -> ActionPlan:
        return build_plan(action_type, resource, params)

    def execute_action(self, plan: ActionPlan) -> ActionResult:
        r = self._world.get(plan.resource_external_id)
        if r is None:
            return ActionResult(ok=False, detail="resource no longer exists")
        c = r.config
        if plan.action_type == "stop_vm":
            c["status"] = "TERMINATED"
        elif plan.action_type == "resize_vm":
            old_v, old_m = c["vcpus"], c["memory_gb"]
            c["machine_type"] = plan.params["machine_type"]
            c["vcpus"], c["memory_gb"] = MACHINES[plan.params["machine_type"]]
            m = self._metrics.get(r.external_id)
            if m:  # the same load on a smaller machine shows as higher utilisation
                for key, ratio in (("cpu_p95", old_v / c["vcpus"]), ("mem_p95", old_m / c["memory_gb"])):
                    if key in m.series:
                        s = m.series[key]
                        m.series[key] = s.model_copy(update={k: min(round(getattr(s, k) * ratio, 1), 100.0)
                                                             for k in ("p95", "avg", "max")})
        elif plan.action_type == "release_ip":
            del self._world[plan.resource_external_id]
        elif plan.action_type == "restrict_firewall":
            if r.labels.get("managed-by") == "legacy-script":
                # Simulated drift: another tool re-applies the old rule right after the change.
                return ActionResult(ok=True, detail="update call accepted (simulated)", observed={"api": "200 OK"})
            c["source_ranges"] = list(plan.params["source_ranges"])
        elif plan.action_type == "remove_public_access":
            for b in c.get("iam_bindings", []):
                b["members"] = [m for m in b["members"] if m not in ("allUsers", "allAuthenticatedUsers")]
            c["iam_bindings"] = [b for b in c.get("iam_bindings", []) if b["members"]]
        else:
            return ActionResult(ok=False, detail=f"unsupported action {plan.action_type}")
        return ActionResult(ok=True, detail="change applied (simulated)", observed={"api": "200 OK"})

    def verify_action(self, plan: ActionPlan) -> Verification:
        ok, observed = expected_state(plan, self.get_resource(plan.resource_external_id))
        return Verification(ok=ok, expected=plan.after, observed=observed,
                            detail="re-read the resource from the simulated inventory and compared it with the plan")
