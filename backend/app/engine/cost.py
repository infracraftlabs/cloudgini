"""Module B: cost optimisation rules. A recommendation needs measured utilisation over a long
enough window; without it the result is 'requires manual review' and carries no savings figure."""
from __future__ import annotations

import math
from typing import Any

from ..providers.base import ResourceMetrics, ResourceRecord
from .common import Draft, ev, is_prod

MetricsMap = dict[str, ResourceMetrics | None]


def _smaller(machine_type: str) -> str | None:
    head, _, size = machine_type.rpartition("-")
    if not size.isdigit() or int(size) <= 2:
        return None
    return f"{head}-{int(size) // 2}"


def _smaller_sql(tier: str) -> str | None:
    parts = tier.split("-")  # db-custom-<vcpus>-<memory MB>
    if len(parts) != 4 or not parts[2].isdigit() or int(parts[2]) <= 1:
        return None
    return f"db-custom-{int(parts[2]) // 2}-{int(parts[3]) // 2}"


def _series(m: ResourceMetrics | None, key: str) -> float | None:
    if m is None or key not in m.series:
        return None
    return m.series[key].p95


def _metric_ev(m: ResourceMetrics, key: str, label: str) -> dict[str, Any]:
    s = m.series[key]
    return ev(label, f"{s.p95:g} {s.unit} (p95), avg {s.avg:g}, max {s.max:g}", f"{s.source}, last {m.observation_days} days")


def _missing(m: ResourceMetrics | None, keys: list[str], min_days: int) -> str | None:
    if m is None:
        return "no utilisation metrics were found for this resource"
    absent = [k for k in keys if k not in m.series or m.series[k].p95 is None]
    if absent:
        return f"metric(s) missing: {', '.join(absent)} (e.g. the monitoring agent isn't installed)"
    if m.observation_days < min_days:
        return f"only {m.observation_days} days of metrics; at least {min_days} are needed"
    return None


def _manual(kind_rule: str, r: ResourceRecord, title: str, reason: str, m: ResourceMetrics | None) -> Draft:
    evidence = [_metric_ev(m, k, k) for k in (m.series if m else {})]
    return Draft(kind="cost", rule=kind_rule, resource_external_id=r.external_id, title=title, severity="info",
                 summary=f"Not enough evidence to recommend a change: {reason}. No savings figure is shown.",
                 current_config={k: r.config.get(k) for k in ("machine_type", "tier", "disk_type", "storage_class") if k in r.config},
                 evidence=evidence, observation_days=m.observation_days if m else None, confidence="low", risk="low",
                 procedure=["Collect utilisation data (install the Ops Agent for memory) and re-scan after the observation window."],
                 manual_review_reason=reason)


def evaluate(resources: list[ResourceRecord], metrics: MetricsMap, t: dict[str, Any]) -> list[Draft]:
    out: list[Draft] = []
    min_days = t["min_observation_days"]
    for r in resources:
        m = metrics.get(r.external_id)
        c = r.config
        if r.resource_type == "vm" and c.get("status") == "RUNNING":
            reason = _missing(m, ["cpu_p95", "mem_p95"], min_days)
            if reason:
                out.append(_manual("vm_rightsize", r, f"Review sizing of VM {r.name}", reason, m))
                continue
            cpu, mem = _series(m, "cpu_p95"), _series(m, "mem_p95")
            evidence = [_metric_ev(m, "cpu_p95", "CPU utilisation"), _metric_ev(m, "mem_p95", "Memory utilisation"),
                        ev("Machine type", f"{c['machine_type']} ({c['vcpus']} vCPU, {c['memory_gb']} GB)", "inventory")]
            if cpu < t["idle_cpu_p95_pct"] and mem < t["idle_mem_p95_pct"]:
                prod = is_prod(r.environment)
                out.append(Draft(
                    kind="cost", rule="vm_idle", resource_external_id=r.external_id, severity="medium",
                    title=f"Stop idle VM {r.name}", evidence=evidence, observation_days=m.observation_days,
                    summary=f"CPU p95 {cpu:g}% and memory p95 {mem:g}% over {m.observation_days} days: the VM looks idle.",
                    current_config={"status": "RUNNING", "machine_type": c["machine_type"]},
                    recommended_config={"status": "TERMINATED"}, savings_config={"status": "TERMINATED"},
                    confidence="high" if m.observation_days >= 30 else "medium", risk="high" if prod else "low",
                    impact="Anything running on the VM stops. Disks and data are kept; it can be started again.",
                    procedure=["Confirm with the owner that nothing needs this VM", "Stop it (dry-run, approve, execute)",
                               "Delete it later through your normal process if it stays unused"],
                    action_type=None if prod else "stop_vm",
                    manual_review_reason="production VM: stop it through your normal change process" if prod else None))
                continue
            target = _smaller(c["machine_type"])
            if target and cpu < t["rightsize_cpu_p95_pct"] and mem < t["rightsize_mem_p95_pct"]:
                prod = is_prod(r.environment)
                out.append(Draft(
                    kind="cost", rule="vm_rightsize", resource_external_id=r.external_id, severity="medium",
                    title=f"Downsize VM {r.name} to {target}", evidence=evidence, observation_days=m.observation_days,
                    summary=(f"CPU p95 {cpu:g}% and memory p95 {mem:g}% over {m.observation_days} days. Half the size "
                             f"would still leave headroom (projected CPU p95 about {min(cpu * 2, 100):g}%)."),
                    current_config={"machine_type": c["machine_type"], "vcpus": c["vcpus"], "memory_gb": c["memory_gb"]},
                    recommended_config={"machine_type": target}, savings_config={"machine_type": target},
                    confidence="high" if m.observation_days >= 30 else "medium", risk="medium" if prod else "low",
                    impact="Needs a restart (a few minutes of downtime). Peaks above the p95 may be slower.",
                    procedure=["Pick a low-traffic window", "Stop the VM", f"Set machine type to {target}",
                               "Start it and watch CPU and latency for a week"],
                    action_type=None if prod else "resize_vm", action_params={"machine_type": target},
                    manual_review_reason=None))
        elif r.resource_type == "disk" and c.get("users") and c.get("disk_type") == "pd-ssd":
            reason = _missing(m, ["iops_p95"], min_days)
            if reason:
                continue  # a disk without IOPS data is simply not assessed
            iops = _series(m, "iops_p95")
            if iops < t["ssd_low_iops"]:
                out.append(Draft(
                    kind="cost", rule="disk_type", resource_external_id=r.external_id, severity="low",
                    title=f"Move disk {r.name} from pd-ssd to pd-balanced",
                    summary=f"p95 of {iops:g} operations/s over {m.observation_days} days is well within pd-balanced limits.",
                    evidence=[_metric_ev(m, "iops_p95", "Disk operations"), ev("Disk", f"{c['size_gb']} GB pd-ssd", "inventory")],
                    observation_days=m.observation_days, current_config={"disk_type": "pd-ssd", "size_gb": c["size_gb"]},
                    recommended_config={"disk_type": "pd-balanced"}, savings_config={"disk_type": "pd-balanced"},
                    confidence="medium", risk="medium",
                    impact="Changing type means snapshot and re-create; the VM is offline while the disk is swapped.",
                    procedure=["Snapshot the disk", "Create a pd-balanced disk from the snapshot",
                               "Stop the VM, swap the disks, start it", "Keep the old disk until checks pass"]))
        elif r.resource_type == "cloudsql":
            reason = _missing(m, ["cpu_p95", "mem_p95"], min_days)
            if reason:
                out.append(_manual("sql_rightsize", r, f"Review sizing of Cloud SQL {r.name}", reason, m))
                continue
            cpu, mem = _series(m, "cpu_p95"), _series(m, "mem_p95")
            target = _smaller_sql(c["tier"])
            if target and cpu < t["rightsize_cpu_p95_pct"] and mem < t["rightsize_mem_p95_pct"]:
                out.append(Draft(
                    kind="cost", rule="sql_rightsize", resource_external_id=r.external_id, severity="medium",
                    title=f"Downsize Cloud SQL {r.name} to {target}",
                    summary=f"CPU p95 {cpu:g}% and memory p95 {mem:g}% over {m.observation_days} days.",
                    evidence=[_metric_ev(m, "cpu_p95", "CPU utilisation"), _metric_ev(m, "mem_p95", "Memory utilisation"),
                              ev("Tier", c["tier"], "inventory")],
                    observation_days=m.observation_days, current_config={"tier": c["tier"]},
                    recommended_config={"tier": target}, savings_config={"tier": target},
                    confidence="medium", risk="high" if is_prod(r.environment) else "medium",
                    impact="Changing tier restarts the instance. Check connection limits and buffer sizes for the smaller tier.",
                    procedure=["Take an on-demand backup", "Schedule the tier change in a maintenance window",
                               "Watch CPU, memory and query latency for a week"]))
        elif r.resource_type == "load_balancer" and c.get("backends"):
            reason = _missing(m, ["requests_per_min"], min_days)
            if reason:
                continue
            rpm = _series(m, "requests_per_min")
            if rpm < 1:
                out.append(Draft(
                    kind="cost", rule="lb_consolidate", resource_external_id=r.external_id, severity="low",
                    title=f"Consolidate low-traffic load balancer {r.name}",
                    summary=f"p95 of {rpm:g} requests/min over {m.observation_days} days on a dedicated load balancer.",
                    evidence=[_metric_ev(m, "requests_per_min", "Requests"), ev("Backends", ", ".join(c["backends"]), "inventory")],
                    observation_days=m.observation_days, current_config={"forwarding_rules": c.get("forwarding_rules")},
                    recommended_config={"forwarding_rules": 0, "note": "serve from a shared load balancer"},
                    savings_full=True, confidence="low", risk="medium",
                    impact="Hostnames and certificates move to the shared load balancer; DNS changes are needed.",
                    procedure=["Add a host rule for this service on the shared load balancer",
                               "Move DNS", "Remove this load balancer's forwarding rule after traffic drains"]))
        elif r.resource_type == "gke_workload":
            reason = _missing(m, ["cpu_usage_m", "mem_usage_mi"], min_days)
            if reason:
                continue
            cpu, mem = _series(m, "cpu_usage_m"), _series(m, "mem_usage_mi")
            if cpu and c["cpu_request_m"] / cpu >= t["gke_request_usage_ratio"]:
                new_cpu = int(math.ceil(cpu * 1.3 / 50) * 50)
                new_mem = int(math.ceil(mem * 1.3 / 64) * 64)
                out.append(Draft(
                    kind="cost", rule="gke_requests", resource_external_id=r.external_id, severity="low",
                    title=f"Lower resource requests for {c['namespace']}/{r.name}",
                    summary=(f"Requests are {c['cpu_request_m']}m CPU / {c['mem_request_mi']}Mi per pod; p95 use is "
                             f"{cpu:g}m / {mem:g}Mi over {m.observation_days} days ({c['replicas']} replicas)."),
                    evidence=[_metric_ev(m, "cpu_usage_m", "CPU used per pod"), _metric_ev(m, "mem_usage_mi", "Memory used per pod"),
                              ev("Requests", f"{c['cpu_request_m']}m CPU, {c['mem_request_mi']}Mi", "Deployment spec")],
                    observation_days=m.observation_days,
                    current_config={"cpu_request_m": c["cpu_request_m"], "mem_request_mi": c["mem_request_mi"]},
                    recommended_config={"cpu_request_m": new_cpu, "mem_request_mi": new_mem, "headroom": "30% over p95"},
                    confidence="medium", risk="medium",
                    impact="Pods pack more densely. Money is saved only if the cluster autoscaler then removes nodes, "
                           "so no savings figure is given.",
                    procedure=["Change requests in the workload's manifest (Git), not in the cluster",
                               "Roll out to one environment first and watch throttling and OOM kills"]))
        elif r.resource_type == "bucket" and c.get("storage_class") == "STANDARD":
            reason = _missing(m, ["reads_per_day"], 30)
            if reason:
                continue
            reads = _series(m, "reads_per_day")
            if reads < t["cold_storage_reads_per_day"] and m.observation_days >= 90:
                out.append(Draft(
                    kind="cost", rule="storage_class", resource_external_id=r.external_id, severity="low",
                    title=f"Move bucket {r.name} to Coldline",
                    summary=f"{reads:g} reads/day (p95) over {m.observation_days} days on {c['size_gb']} GB of Standard storage.",
                    evidence=[_metric_ev(m, "reads_per_day", "Read requests"), ev("Storage", f"{c['size_gb']} GB STANDARD", "inventory")],
                    observation_days=m.observation_days, current_config={"storage_class": "STANDARD"},
                    recommended_config={"storage_class": "COLDLINE"}, savings_config={"storage_class": "COLDLINE"},
                    confidence="medium", risk="low",
                    impact="Coldline has a 90-day minimum storage duration and charges per GB read. Savings exclude retrieval fees.",
                    procedure=["Add a lifecycle rule (SetStorageClass COLDLINE after N days) rather than rewriting objects",
                               "Check nobody needs frequent reads (e.g. log queries)"]))
    return out
