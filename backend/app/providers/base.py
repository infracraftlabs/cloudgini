"""Provider interfaces. Each cloud (GCP today, AWS and Azure later) implements these four.

Everything a provider returns is labelled with `data_source` ("real" or "simulated"), and
anything it cannot measure is returned as None: the engine never fills gaps with guesses.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class ResourceRecord(BaseModel):
    external_id: str
    name: str
    resource_type: str  # vm, disk, cloudsql, load_balancer, gke_workload, bucket, static_ip, snapshot, image, firewall_rule, iam_policy, service_account
    project: str
    region: str | None = None
    environment: str = "unknown"  # from the `env`/`environment` label; unknown when missing
    owner: str | None = None  # from the `owner` label
    labels: dict[str, str] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    data_source: str


class MetricSeries(BaseModel):
    p95: float | None = None
    avg: float | None = None
    max: float | None = None
    unit: str
    source: str  # where it came from, e.g. the Cloud Monitoring metric type


class ResourceMetrics(BaseModel):
    observation_days: int
    series: dict[str, MetricSeries]
    data_source: str


class CostRecord(BaseModel):
    day: date
    service: str
    project: str
    environment: str
    cost: float
    currency: str = "USD"
    resource_external_id: str | None = None


class CostData(BaseModel):
    records: list[CostRecord]
    basis: str  # "billing_export" or "simulated_billing"; "none" when unavailable
    data_source: str
    note: str | None = None


class CostEstimate(BaseModel):
    monthly: float
    method: str  # plain-English description of how the number was produced


class ProviderFinding(BaseModel):
    """A finding produced by the cloud's own security service (e.g. Security Command Center)."""
    external_id: str
    category: str
    severity: str
    resource_external_id: str | None
    description: str
    data_source: str


class ActionPlan(BaseModel):
    action_type: str
    resource_external_id: str
    params: dict[str, Any] = Field(default_factory=dict)
    steps: list[str]
    before: dict[str, Any]
    after: dict[str, Any]
    preconditions: list[str]
    reversible: bool
    destructive: bool
    rollback: str


class ActionResult(BaseModel):
    ok: bool
    detail: str
    observed: dict[str, Any] = Field(default_factory=dict)


class Verification(BaseModel):
    ok: bool
    expected: dict[str, Any]
    observed: dict[str, Any]
    detail: str


class CloudInventoryProvider(ABC):
    @abstractmethod
    def list_resources(self) -> list[ResourceRecord]: ...

    @abstractmethod
    def get_resource(self, external_id: str) -> ResourceRecord | None: ...

    @abstractmethod
    def get_resource_metrics(self, resource: ResourceRecord) -> ResourceMetrics | None: ...


class CloudCostProvider(ABC):
    @abstractmethod
    def get_cost_data(self, start: date, end: date) -> CostData: ...

    @abstractmethod
    def estimate_resource_cost(self, resource: ResourceRecord, config: dict[str, Any], current_monthly: float) -> CostEstimate | None:
        """Monthly cost of `resource` if it had `config`, or None when it can't be estimated honestly."""


class CloudSecurityProvider(ABC):
    @abstractmethod
    def get_security_findings(self) -> list[ProviderFinding]: ...

    def evaluate_security_rules(self, resources: list[ResourceRecord], thresholds: dict[str, Any]) -> list:
        from ..engine import security

        return security.evaluate(resources, thresholds)


class CloudRemediationProvider(ABC):
    @abstractmethod
    def plan_action(self, action_type: str, resource: ResourceRecord, params: dict[str, Any]) -> ActionPlan: ...

    @abstractmethod
    def execute_action(self, plan: ActionPlan) -> ActionResult: ...

    @abstractmethod
    def verify_action(self, plan: ActionPlan) -> Verification: ...


class CloudProvider(CloudInventoryProvider, CloudCostProvider, CloudSecurityProvider, CloudRemediationProvider, ABC):
    name: str
    data_source: str
