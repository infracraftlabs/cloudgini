from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AccountOut(ORM):
    id: str
    provider: str
    name: str
    scope_id: str
    data_source: str
    remediation_enabled: bool
    status: str
    status_detail: str | None
    last_scan_at: datetime | None


class AccountPatch(BaseModel):
    remediation_enabled: bool


class ResourceOut(ORM):
    id: int
    account_id: str
    external_id: str
    name: str
    resource_type: str
    project: str
    region: str | None
    environment: str
    owner: str | None
    labels: dict[str, Any]
    config: dict[str, Any]
    metrics: dict[str, Any] | None
    monthly_cost: float | None
    cost_basis: str
    data_source: str


class RecommendationOut(ORM):
    id: str
    account_id: str
    resource_id: int | None
    kind: str
    rule: str
    title: str
    summary: str
    severity: str
    state: str
    current_config: dict[str, Any]
    recommended_config: dict[str, Any]
    evidence: list[dict[str, Any]]
    checks: list[dict[str, Any]]
    observation_days: int | None
    monthly_savings: float | None
    savings_basis: str
    savings_method: str | None
    confidence: str
    risk: str
    impact: str
    procedure: list[str]
    action_type: str | None
    action_params: dict[str, Any]
    manual_review_reason: str | None
    verification: dict[str, Any] | None
    data_source: str
    detected_at: datetime
    updated_at: datetime
    resource_name: str | None = None
    resource_type: str | None = None
    project: str | None = None
    environment: str | None = None
    provider: str | None = None


class ActionOut(ORM):
    id: str
    recommendation_id: str
    action_type: str
    params: dict[str, Any]
    state: str
    plan: dict[str, Any]
    reversible: bool
    destructive: bool
    rollback: str
    requested_by: str
    approved_by: str | None
    executed_by: str | None
    result: dict[str, Any] | None
    verification: dict[str, Any] | None
    error: str | None
    data_source: str
    created_at: datetime
    updated_at: datetime


class AuditOut(ORM):
    id: int
    ts: datetime
    actor: str
    role: str
    event: str
    target_type: str
    target_id: str
    outcome: str
    details: dict[str, Any]


class TransitionIn(BaseModel):
    to: Literal["reviewed", "rejected", "requires_manual_review", "detected", "approved"]
    note: str | None = Field(None, max_length=1000)


class NoteIn(BaseModel):
    note: str = Field(..., min_length=3, max_length=1000)


class PlanIn(BaseModel):
    machine_type: str | None = Field(None, pattern=r"^[a-z0-9-]{3,40}$")
    source_ranges: list[str] | None = Field(None, max_length=10)

    def params(self) -> dict[str, Any]:
        return {k: v for k, v in self.model_dump().items() if v is not None}


class ApproveIn(BaseModel):
    confirm: str | None = Field(None, max_length=256, description="For irreversible actions: the resource name")


class AssistantIn(BaseModel):
    question: str = Field(..., min_length=2, max_length=2000)
    recommendation_id: str | None = Field(None, max_length=32)


class ThresholdsIn(BaseModel):
    min_observation_days: int = Field(14, ge=7, le=90)
    rightsize_cpu_p95_pct: float = Field(40, ge=5, le=90)
    rightsize_mem_p95_pct: float = Field(50, ge=5, le=90)
    idle_cpu_p95_pct: float = Field(5, ge=0, le=30)
    idle_mem_p95_pct: float = Field(20, ge=0, le=50)
    unattached_disk_days: int = Field(30, ge=7, le=365)
    snapshot_retention_days: int = Field(90, ge=30, le=3650)
    image_age_days: int = Field(180, ge=30, le=3650)
    abandoned_days: int = Field(30, ge=7, le=365)
    sa_key_max_age_days: int = Field(90, ge=30, le=730)
    gke_request_usage_ratio: float = Field(3.0, ge=1.5, le=20)
    cold_storage_reads_per_day: float = Field(1, ge=0, le=100)
    ssd_low_iops: float = Field(500, ge=10, le=100000)


class Filters(BaseModel):
    provider: str | None = None
    account_id: str | None = None
    project: str | None = None
    environment: str | None = None
    resource_type: str | None = None
    state: str | None = None
    date_from: date | None = None
    date_to: date | None = None
