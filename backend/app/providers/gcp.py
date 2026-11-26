"""GCP provider (experimental). Read-only discovery through Cloud Asset Inventory, utilisation
through Cloud Monitoring, cost through the BigQuery billing export, and findings from Security
Command Center when it is enabled. Remediation uses the Compute Engine and Cloud Storage APIs
for the four allow-listed action types only.

Credentials: Application Default Credentials. CloudGini never reads or stores key files.
Anything that can't be read (API disabled, permission missing, no billing export) is reported
as missing, never guessed.
"""
from __future__ import annotations

import logging
import math
from datetime import date, datetime, timedelta, timezone
from typing import Any

from ..engine.actions import PUBLIC_MEMBERS, build_plan, expected_state
from .base import (ActionPlan, ActionResult, CloudProvider, CostData, CostEstimate, CostRecord, MetricSeries,
                   ProviderFinding, ResourceMetrics, ResourceRecord, Verification)

log = logging.getLogger("cloudgini.gcp")
DS = "real"

ASSET_TYPES = [
    "compute.googleapis.com/Instance", "compute.googleapis.com/Disk", "compute.googleapis.com/Address",
    "compute.googleapis.com/GlobalAddress", "compute.googleapis.com/Snapshot", "compute.googleapis.com/Image",
    "compute.googleapis.com/Firewall", "compute.googleapis.com/InstanceTemplate", "compute.googleapis.com/ForwardingRule",
    "compute.googleapis.com/GlobalForwardingRule", "compute.googleapis.com/TargetHttpProxy",
    "compute.googleapis.com/TargetHttpsProxy", "compute.googleapis.com/UrlMap", "compute.googleapis.com/BackendService",
    "storage.googleapis.com/Bucket", "sqladmin.googleapis.com/Instance", "iam.googleapis.com/ServiceAccount",
    "iam.googleapis.com/ServiceAccountKey", "apps.k8s.io/Deployment",
]


def last(url: str | None) -> str:
    return (url or "").rstrip("/").rsplit("/", 1)[-1]


def env_of(labels: dict[str, str]) -> str:
    return (labels.get("env") or labels.get("environment") or "unknown").lower()


def p95(values: list[float]) -> float | None:
    if not values:
        return None
    s = sorted(values)
    return s[min(len(s) - 1, math.ceil(0.95 * len(s)) - 1)]


def _rr(name: str, rtype: str, project: str, data: dict[str, Any], config: dict[str, Any], region: str | None,
        labels: dict[str, str] | None = None) -> ResourceRecord:
    labels = labels if labels is not None else (data.get("labels") or {})
    return ResourceRecord(external_id=name, name=data.get("name") or last(name), resource_type=rtype, project=project,
                          region=region, environment=env_of(labels), owner=labels.get("owner"), labels=labels,
                          config=config, data_source=DS)


def normalise(project: str, assets: list[dict[str, Any]], policies: dict[str, list[dict[str, Any]]],
              project_policy: dict[str, Any] | None, machine_specs: dict[str, tuple[int, float]] | None = None) -> list[ResourceRecord]:
    """Turn Cloud Asset Inventory records ({name, asset_type, data}) into CloudGini resources.
    Pure function, so it is tested with recorded fixtures."""
    machine_specs = machine_specs or {}
    by_type: dict[str, list[dict[str, Any]]] = {}
    for a in assets:
        by_type.setdefault(a["asset_type"], []).append(a)
    self_links = {a["data"].get("selfLink"): a for a in assets if a["data"].get("selfLink")}
    disks = by_type.get("compute.googleapis.com/Disk", [])
    disk_links = {d["data"].get("selfLink") for d in disks}
    images_in_use = {d["data"].get("sourceImage") for d in disks} | {
        dd.get("initializeParams", {}).get("sourceImage")
        for t in by_type.get("compute.googleapis.com/InstanceTemplate", [])
        for dd in t["data"].get("properties", {}).get("disks", [])}
    attached: dict[str, tuple[str, str]] = {}  # disk selfLink -> (instance id, device name)
    for a in by_type.get("compute.googleapis.com/Instance", []):
        for dd in a["data"].get("disks", []):
            attached[dd.get("source")] = (a["data"].get("id"), dd.get("deviceName"))
    out: list[ResourceRecord] = []

    for a in by_type.get("compute.googleapis.com/Instance", []):
        d = a["data"]
        mtype = last(d.get("machineType"))
        zone = last(d.get("zone"))
        vcpus, mem = machine_specs.get(f"{zone}/{mtype}", (None, None))
        out.append(_rr(a["name"], "vm", project, d, {
            "machine_type": mtype, "vcpus": vcpus, "memory_gb": mem, "status": d.get("status"), "zone": zone,
            "instance_id": d.get("id"), "last_stop": d.get("lastStopTimestamp"),
            "tags": (d.get("tags") or {}).get("items", [])}, zone[:-2] if zone else None))
    for a in disks:
        d = a["data"]
        zone = last(d.get("zone"))
        out.append(_rr(a["name"], "disk", project, d, {
            "size_gb": int(d.get("sizeGb", 0)), "disk_type": last(d.get("type")), "users": [last(u) for u in d.get("users", [])],
            "last_detach": d.get("lastDetachTimestamp"), "last_attach": d.get("lastAttachTimestamp"), "created": d.get("creationTimestamp"), "zone": zone,
            "attached_instance_id": attached.get(d.get("selfLink"), (None, None))[0],
            "device_name": attached.get(d.get("selfLink"), (None, None))[1]},
            zone[:-2] if zone else None))
    for t in ("compute.googleapis.com/Address", "compute.googleapis.com/GlobalAddress"):
        for a in by_type.get(t, []):
            d = a["data"]
            out.append(_rr(a["name"], "static_ip", project, d, {
                "address": d.get("address"), "status": d.get("status"), "address_type": d.get("addressType"),
                "users": [last(u) for u in d.get("users", [])], "reserved_at": d.get("creationTimestamp"),
                "region": last(d.get("region")) or "global"}, last(d.get("region")) or "global"))
    image_sources = {i["data"].get("sourceSnapshot") for i in by_type.get("compute.googleapis.com/Image", [])}
    for a in by_type.get("compute.googleapis.com/Snapshot", []):
        d = a["data"]
        out.append(_rr(a["name"], "snapshot", project, d, {
            "source_disk": last(d.get("sourceDisk")), "source_disk_exists": d.get("sourceDisk") in disk_links,
            "created": d.get("creationTimestamp"), "size_gb": int(d.get("diskSizeGb", 0)),
            "used_by_images": ["image"] if d.get("selfLink") in image_sources else [],
            "snapshot_schedule": "auto" if d.get("autoCreated") else None}, None))
    for a in by_type.get("compute.googleapis.com/Image", []):
        d = a["data"]
        out.append(_rr(a["name"], "image", project, d, {
            "created": d.get("creationTimestamp"), "family": d.get("family"),
            "deprecated": (d.get("deprecated") or {}).get("state"), "size_gb": int(d.get("diskSizeGb", 0)),
            "used_by": ["disk-or-template"] if d.get("selfLink") in images_in_use else []}, None))
    for a in by_type.get("compute.googleapis.com/Firewall", []):
        d = a["data"]
        allowed = [{"protocol": x.get("IPProtocol"), "ports": x.get("ports", [])} for x in d.get("allowed", [])]
        out.append(_rr(a["name"], "firewall_rule", project, d, {
            "direction": d.get("direction"), "source_ranges": d.get("sourceRanges", []), "allowed": allowed,
            "target_tags": d.get("targetTags", []), "disabled": d.get("disabled", False), "network": last(d.get("network"))},
            "global", labels=_desc_labels(d.get("description"))))
    for t in ("compute.googleapis.com/GlobalForwardingRule", "compute.googleapis.com/ForwardingRule"):
        for a in by_type.get(t, []):
            d = a["data"]
            if d.get("loadBalancingScheme") not in ("EXTERNAL", "EXTERNAL_MANAGED", "INTERNAL_MANAGED"):
                continue
            out.append(_rr(a["name"], "load_balancer", project, d, {
                "scheme": d.get("loadBalancingScheme"), "forwarding_rules": 1, "ip": d.get("IPAddress"),
                "backends": _lb_backends(d, self_links)}, last(d.get("region")) or "global"))
    for a in by_type.get("storage.googleapis.com/Bucket", []):
        d = a["data"]
        out.append(_rr(a["name"], "bucket", project, d, {
            "storage_class": d.get("storageClass"), "size_gb": None,
            "uniform_access": ((d.get("iamConfiguration") or {}).get("uniformBucketLevelAccess") or {}).get("enabled"),
            "public_access_prevention": (d.get("iamConfiguration") or {}).get("publicAccessPrevention"),
            "encryption": "cmek" if (d.get("encryption") or {}).get("defaultKmsKeyName") else "google-managed",
            "iam_bindings": policies.get(a["name"], [])}, (d.get("location") or "").lower()))
    for a in by_type.get("sqladmin.googleapis.com/Instance", []):
        d = a["data"]
        s = d.get("settings", {})
        ip = s.get("ipConfiguration", {})
        tier = s.get("tier", "")
        parts = tier.split("-")
        vcpus, mem = (int(parts[2]), int(parts[3]) / 1024) if len(parts) == 4 and parts[1] == "custom" else (None, None)
        ssl = ip.get("requireSsl") or ip.get("sslMode") in ("ENCRYPTED_ONLY", "TRUSTED_CLIENT_CERTIFICATE_REQUIRED")
        out.append(_rr(a["name"], "cloudsql", project, d, {
            "tier": tier, "vcpus": vcpus, "memory_gb": mem, "public_ip": ip.get("ipv4Enabled", False),
            "authorized_networks": [n.get("value") for n in ip.get("authorizedNetworks", [])], "ssl_required": bool(ssl),
            "backups_enabled": (s.get("backupConfiguration") or {}).get("enabled"), "database_version": d.get("databaseVersion"),
            "database_id": f"{project}:{d.get('name')}"}, d.get("region"), labels=s.get("userLabels") or {}))
    bindings = (project_policy or {}).get("bindings", [])
    keys_by_sa: dict[str, list[dict[str, Any]]] = {}
    for a in by_type.get("iam.googleapis.com/ServiceAccountKey", []):
        d = a["data"]
        sa = a["name"].split("/serviceAccounts/")[1].split("/")[0] if "/serviceAccounts/" in a["name"] else ""
        keys_by_sa.setdefault(sa, []).append({"id": last(a["name"]), "type": d.get("keyType"), "created": d.get("validAfterTime")})
    for a in by_type.get("iam.googleapis.com/ServiceAccount", []):
        d = a["data"]
        email = d.get("email", "")
        roles = sorted({b["role"] for b in bindings if f"serviceAccount:{email}" in b.get("members", [])})
        keys = keys_by_sa.get(email, []) + keys_by_sa.get(d.get("uniqueId", ""), [])
        rec = _rr(a["name"], "service_account", project, d, {"roles": roles, "disabled": d.get("disabled", False),
                                                              "keys": [k for k in keys if k["type"] == "USER_MANAGED"]},
                  "global", labels=_desc_labels(d.get("description")))
        out.append(rec.model_copy(update={"name": email or rec.name}))
    for a in by_type.get("apps.k8s.io/Deployment", []):
        d = a["data"]
        containers = d.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        cpu = sum(_cpu_m((c.get("resources") or {}).get("requests", {}).get("cpu")) for c in containers)
        mem = sum(_mem_mi((c.get("resources") or {}).get("requests", {}).get("memory")) for c in containers)
        meta = d.get("metadata", {})
        cluster = a["name"].split("/clusters/")[1].split("/")[0] if "/clusters/" in a["name"] else ""
        out.append(_rr(a["name"], "gke_workload", project, meta, {
            "cluster": cluster, "namespace": meta.get("namespace"), "replicas": d.get("spec", {}).get("replicas", 1),
            "cpu_request_m": cpu, "mem_request_mi": mem}, None, labels=meta.get("labels") or {}))
    if project_policy is not None:
        out.append(ResourceRecord(
            external_id=f"//cloudresourcemanager.googleapis.com/projects/{project}", name=project, resource_type="iam_policy",
            project=project, region="global", environment="unknown", labels={}, data_source=DS,
            config={"bindings": [{"role": b["role"], "members": b.get("members", [])} for b in bindings],
                    "audit_configs": [{"service": c.get("service"), "log_types": [x.get("logType") for x in c.get("auditLogConfigs", [])]}
                                      for c in project_policy.get("auditConfigs", [])]}))
    return out


def _desc_labels(desc: str | None) -> dict[str, str]:
    """Firewall rules and service accounts have no labels; read `key=value` pairs from the description."""
    out = {}
    for part in (desc or "").replace(";", " ").split():
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip().lower()] = v.strip()
    return out


def _lb_backends(rule: dict[str, Any], links: dict[str, dict[str, Any]]) -> list[str]:
    proxy = links.get(rule.get("target"))
    url_map = links.get((proxy or {}).get("data", {}).get("urlMap"))
    svc_links = {(url_map or {}).get("data", {}).get("defaultService")}
    for pm in (url_map or {}).get("data", {}).get("pathMatchers", []):
        svc_links.add(pm.get("defaultService"))
    out = []
    for s in filter(None, svc_links):
        svc = links.get(s)
        out += [last(b.get("group")) for b in (svc or {}).get("data", {}).get("backends", [])]
    return out


def _cpu_m(v: str | None) -> int:
    if not v:
        return 0
    return int(v[:-1]) if v.endswith("m") else int(float(v) * 1000)


def _mem_mi(v: str | None) -> int:
    if not v:
        return 0
    units = {"Ki": 1 / 1024, "Mi": 1, "Gi": 1024, "K": 1 / 1024, "M": 1, "G": 1024}
    for u, f in units.items():
        if v.endswith(u):
            return int(float(v[: -len(u)]) * f)
    return int(int(v) / 1024 / 1024)


class GcpProvider(CloudProvider):
    name = "gcp"
    data_source = DS

    def __init__(self, project_id: str, billing_table: str | None = None) -> None:
        self.project = project_id
        self.billing_table = billing_table
        self._resources: dict[str, ResourceRecord] = {}

    # ------------------------------------------------------------- inventory
    def list_resources(self) -> list[ResourceRecord]:
        from google.cloud import asset_v1

        client = asset_v1.AssetServiceClient()
        parent = f"projects/{self.project}"
        assets = []
        for a in client.list_assets(request={"parent": parent, "asset_types": ASSET_TYPES,
                                             "content_type": asset_v1.ContentType.RESOURCE}):
            d = _to_dict(a)
            assets.append({"name": d["name"], "asset_type": d["assetType"], "data": d.get("resource", {}).get("data", {})})
        policies: dict[str, list[dict[str, Any]]] = {}
        project_policy = None
        for a in client.list_assets(request={"parent": parent, "content_type": asset_v1.ContentType.IAM_POLICY,
                                             "asset_types": ["storage.googleapis.com/Bucket",
                                                             "cloudresourcemanager.googleapis.com/Project"]}):
            d = _to_dict(a)
            pol = d.get("iamPolicy", {})
            if d["assetType"].startswith("cloudresourcemanager"):
                project_policy = pol
            else:
                policies[d["name"]] = pol.get("bindings", [])
        if project_policy is None:
            project_policy = {"bindings": [], "auditConfigs": []}
        resources = normalise(self.project, assets, policies, project_policy, self._machine_specs(assets))
        self._resources = {r.external_id: r for r in resources}
        return resources

    def _machine_specs(self, assets: list[dict[str, Any]]) -> dict[str, tuple[int, float]]:
        from google.cloud import compute_v1

        client = compute_v1.MachineTypesClient()
        out: dict[str, tuple[int, float]] = {}
        for a in assets:
            if a["asset_type"] != "compute.googleapis.com/Instance":
                continue
            zone, mtype = last(a["data"].get("zone")), last(a["data"].get("machineType"))
            key = f"{zone}/{mtype}"
            if key not in out:
                try:
                    mt = client.get(project=self.project, zone=zone, machine_type=mtype)
                    out[key] = (mt.guest_cpus, round(mt.memory_mb / 1024, 2))
                except Exception as e:  # leave unknown rather than guess
                    log.warning("machine type %s: %s", key, e)
        return out

    def get_resource(self, external_id: str) -> ResourceRecord | None:
        """Fresh read straight from the service API (Asset Inventory can lag by minutes)."""
        cached = self._resources.get(external_id)
        if cached is None:
            return None
        from google.api_core.exceptions import NotFound
        from google.cloud import compute_v1, storage

        c = dict(cached.config)
        try:
            if cached.resource_type == "vm":
                i = compute_v1.InstancesClient().get(project=self.project, zone=c["zone"], instance=cached.name)
                c.update(status=i.status, machine_type=last(i.machine_type))
            elif cached.resource_type == "static_ip":
                region = c.get("region", "global")
                a = (compute_v1.GlobalAddressesClient().get(project=self.project, address=cached.name) if region == "global"
                     else compute_v1.AddressesClient().get(project=self.project, region=region, address=cached.name))
                c.update(status=a.status, users=[last(u) for u in a.users])
            elif cached.resource_type == "firewall_rule":
                f = compute_v1.FirewallsClient().get(project=self.project, firewall=cached.name)
                c.update(source_ranges=list(f.source_ranges), disabled=f.disabled)
            elif cached.resource_type == "bucket":
                pol = storage.Client(project=self.project).bucket(cached.name).get_iam_policy(requested_policy_version=3)
                c["iam_bindings"] = [{"role": b["role"], "members": sorted(b["members"])} for b in pol.bindings]
        except NotFound:
            return None
        return cached.model_copy(update={"config": c})

    def get_resource_metrics(self, resource: ResourceRecord) -> ResourceMetrics | None:
        try:
            return self._metrics(resource)
        except Exception as e:
            log.warning("metrics for %s: %s", resource.external_id, e)
            return None

    def _metrics(self, r: ResourceRecord) -> ResourceMetrics | None:
        c = r.config
        q: dict[str, tuple[str, str, float, str]] = {}  # key -> (filter, unit, scale, reducer)
        if r.resource_type == "vm" and c.get("status") == "RUNNING" and c.get("instance_id"):
            iid = c["instance_id"]
            q["cpu_p95"] = (f'metric.type="compute.googleapis.com/instance/cpu/utilization" AND resource.labels.instance_id="{iid}"', "%", 100, "mean")
            q["mem_p95"] = (f'metric.type="agent.googleapis.com/memory/percent_used" AND metric.labels.state="used" AND resource.labels.instance_id="{iid}"', "%", 1, "mean")
        elif r.resource_type == "cloudsql":
            dbid = c["database_id"]
            q["cpu_p95"] = (f'metric.type="cloudsql.googleapis.com/database/cpu/utilization" AND resource.labels.database_id="{dbid}"', "%", 100, "mean")
            q["mem_p95"] = (f'metric.type="cloudsql.googleapis.com/database/memory/utilization" AND resource.labels.database_id="{dbid}"', "%", 100, "mean")
        elif r.resource_type == "disk" and c.get("attached_instance_id") and c.get("device_name"):
            q["iops_p95"] = ('metric.type=one_of("compute.googleapis.com/instance/disk/read_ops_count",'
                             '"compute.googleapis.com/instance/disk/write_ops_count") AND '
                             f'resource.labels.instance_id="{c["attached_instance_id"]}" AND metric.labels.device_name="{c["device_name"]}"',
                             "ops/s", 1, "rate")
        elif r.resource_type == "load_balancer":
            q["requests_per_min"] = (f'metric.type="loadbalancing.googleapis.com/https/request_count" AND resource.labels.forwarding_rule_name="{r.name}"', "req/min", 60, "rate")
        elif r.resource_type == "bucket":
            q["reads_per_day"] = (f'metric.type="storage.googleapis.com/api/request_count" AND metric.labels.method="ReadObject" AND resource.labels.bucket_name="{r.name}"', "requests/day", 86400, "rate")
        if not q:
            return None
        series: dict[str, MetricSeries] = {}
        days = 0
        for key, (flt, unit, scale, reducer) in q.items():
            pts = self._hourly_points(flt, reducer, 30)
            if not pts:
                continue
            values = [v * scale for _, v in pts]
            span = (max(t for t, _ in pts) - min(t for t, _ in pts)).days + 1
            days = max(days, span)
            series[key] = MetricSeries(p95=round(p95(values), 2), avg=round(sum(values) / len(values), 2),
                                       max=round(max(values), 2), unit=unit, source=flt.split('"')[1])
        return ResourceMetrics(observation_days=days, series=series, data_source=DS) if series else None

    def _hourly_points(self, flt: str, reducer: str, days: int) -> list[tuple[datetime, float]]:
        from google.cloud import monitoring_v3

        client = monitoring_v3.MetricServiceClient()
        now = datetime.now(timezone.utc)
        interval = monitoring_v3.TimeInterval(end_time=now, start_time=now - timedelta(days=days))
        aligner = (monitoring_v3.Aggregation.Aligner.ALIGN_RATE if reducer == "rate"
                   else monitoring_v3.Aggregation.Aligner.ALIGN_MEAN)
        agg = monitoring_v3.Aggregation(alignment_period={"seconds": 3600}, per_series_aligner=aligner,
                                        cross_series_reducer=monitoring_v3.Aggregation.Reducer.REDUCE_SUM)
        out = []
        for ts in client.list_time_series(name=f"projects/{self.project}", filter=flt, interval=interval, aggregation=agg,
                                          view=monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL):
            for p in ts.points:
                v = p.value.double_value or float(p.value.int64_value)
                out.append((p.interval.end_time, v))
        return out

    # ------------------------------------------------------------- cost
    def get_cost_data(self, start: date, end: date) -> CostData:
        if not self.billing_table:
            return CostData(records=[], basis="none", data_source=DS,
                            note="No billing export configured (CLOUDGINI_GCP_BILLING_TABLE): no cost or savings figures.")
        from google.cloud import bigquery

        resource_level = "resource" in self.billing_table.rsplit(".", 1)[-1]
        res_col = "resource.global_name" if resource_level else "CAST(NULL AS STRING)"
        sql = f"""
            SELECT DATE(usage_start_time) AS day, service.description AS service, project.id AS project,
                   IFNULL((SELECT value FROM UNNEST(labels) WHERE key IN ('env','environment') LIMIT 1), 'unknown') AS env,
                   {res_col} AS resource, currency,
                   SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) AS cost
            FROM `{self.billing_table}`
            WHERE project.id = @project AND DATE(usage_start_time) BETWEEN @start AND @end
            GROUP BY day, service, project, env, resource, currency"""
        job = bigquery.Client(project=self.project).query(sql, job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("project", "STRING", self.project),
            bigquery.ScalarQueryParameter("start", "DATE", start), bigquery.ScalarQueryParameter("end", "DATE", end)]))
        aliases = self._billing_aliases()
        records = [CostRecord(day=row.day, service=row.service, project=row.project, environment=row.env, cost=float(row.cost),
                              currency=row.currency, resource_external_id=aliases.get(row.resource, row.resource))
                   for row in job.result()]
        note = None if resource_level else "Standard billing export: costs are per service, not per resource, so no savings figures."
        return CostData(records=records, basis="billing_export", data_source=DS, note=note)

    def _billing_aliases(self) -> dict[str, str]:
        """Billing uses numeric IDs for VMs (…/instances/<id>); Asset Inventory uses names."""
        out = {}
        for r in self._resources.values():
            if r.resource_type == "vm" and r.config.get("instance_id"):
                out[r.external_id.rsplit("/", 1)[0] + "/" + str(r.config["instance_id"])] = r.external_id
        return out

    def estimate_resource_cost(self, resource: ResourceRecord, config: dict[str, Any], current_monthly: float) -> CostEstimate | None:
        c = resource.config
        if resource.resource_type == "vm" and config.get("status") == "TERMINATED":
            return CostEstimate(monthly=0.0, method="a stopped VM stops vCPU and memory charges; its disks are billed separately and are not counted")
        if resource.resource_type == "vm" and "machine_type" in config and c.get("vcpus"):
            head = c["machine_type"].rsplit("-", 1)
            new = config["machine_type"].rsplit("-", 1)
            if head[0] == new[0] and new[1].isdigit():
                return CostEstimate(monthly=round(current_monthly * int(new[1]) / c["vcpus"], 2),
                                    method="billed cost scaled by vCPU count within the same machine family (assumes the family's fixed memory ratio)")
        if resource.resource_type == "cloudsql" and "tier" in config and c.get("vcpus"):
            new = config["tier"].split("-")
            return CostEstimate(monthly=round(current_monthly * int(new[2]) / c["vcpus"], 2),
                                method="billed cost scaled by vCPU count for a db-custom tier with proportional memory; storage excluded")
        return None  # disk types, storage classes etc. need list prices, which CloudGini doesn't guess

    # ------------------------------------------------------------- security
    def get_security_findings(self) -> list[ProviderFinding]:
        try:
            from google.cloud import securitycenter_v1

            client = securitycenter_v1.SecurityCenterClient()
            out = []
            for res in client.list_findings(request={"parent": f"projects/{self.project}/sources/-", "filter": 'state="ACTIVE"'}):
                f = res.finding
                out.append(ProviderFinding(external_id=f.name, category=f.category, severity=f.severity.name,
                                           resource_external_id=f.resource_name or None, description=f.description or f.category,
                                           data_source=DS))
            return out
        except Exception as e:  # SCC not enabled or no permission: CloudGini's own rules still run
            log.info("Security Command Center unavailable for %s: %s", self.project, e)
            return []

    # ------------------------------------------------------------- remediation
    def plan_action(self, action_type: str, resource: ResourceRecord, params: dict[str, Any]) -> ActionPlan:
        return build_plan(action_type, resource, params)

    def execute_action(self, plan: ActionPlan) -> ActionResult:
        from google.cloud import compute_v1, storage

        r = self._resources.get(plan.resource_external_id)
        if r is None:
            return ActionResult(ok=False, detail="resource not in the last inventory; scan again")
        c = r.config
        try:
            if plan.action_type == "stop_vm":
                compute_v1.InstancesClient().stop(project=self.project, zone=c["zone"], instance=r.name).result(timeout=300)
            elif plan.action_type == "resize_vm":
                ic = compute_v1.InstancesClient()
                was_running = ic.get(project=self.project, zone=c["zone"], instance=r.name).status == "RUNNING"
                if was_running:
                    ic.stop(project=self.project, zone=c["zone"], instance=r.name).result(timeout=300)
                ic.set_machine_type(project=self.project, zone=c["zone"], instance=r.name,
                                    instances_set_machine_type_request_resource=compute_v1.InstancesSetMachineTypeRequest(
                                        machine_type=f"zones/{c['zone']}/machineTypes/{plan.params['machine_type']}")).result(timeout=300)
                if was_running:
                    ic.start(project=self.project, zone=c["zone"], instance=r.name).result(timeout=300)
            elif plan.action_type == "release_ip":
                region = c.get("region", "global")
                op = (compute_v1.GlobalAddressesClient().delete(project=self.project, address=r.name) if region == "global"
                      else compute_v1.AddressesClient().delete(project=self.project, region=region, address=r.name))
                op.result(timeout=300)
            elif plan.action_type == "restrict_firewall":
                compute_v1.FirewallsClient().patch(project=self.project, firewall=r.name,
                                                   firewall_resource=compute_v1.Firewall(source_ranges=plan.params["source_ranges"])).result(timeout=300)
            elif plan.action_type == "remove_public_access":
                bucket = storage.Client(project=self.project).bucket(r.name)
                pol = bucket.get_iam_policy(requested_policy_version=3)
                for b in pol.bindings:
                    b["members"] = {m for m in b["members"] if m not in PUBLIC_MEMBERS}
                pol.bindings = [b for b in pol.bindings if b["members"]]
                bucket.set_iam_policy(pol)
            else:
                return ActionResult(ok=False, detail=f"unsupported action {plan.action_type}")
        except Exception as e:
            return ActionResult(ok=False, detail=f"{type(e).__name__}: {e}"[:1000])
        return ActionResult(ok=True, detail="API call completed")

    def verify_action(self, plan: ActionPlan) -> Verification:
        ok, observed = expected_state(plan, self.get_resource(plan.resource_external_id))
        return Verification(ok=ok, expected=plan.after, observed=observed,
                            detail="re-read the resource directly from the service API and compared it with the plan")


def _to_dict(asset) -> dict[str, Any]:
    from google.cloud import asset_v1
    from google.protobuf.json_format import MessageToDict

    return MessageToDict(asset_v1.Asset.pb(asset))
