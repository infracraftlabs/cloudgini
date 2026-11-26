from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

DEFAULT_THRESHOLDS: dict[str, Any] = {
    "min_observation_days": 14,
    "rightsize_cpu_p95_pct": 40,
    "rightsize_mem_p95_pct": 50,
    "idle_cpu_p95_pct": 5,
    "idle_mem_p95_pct": 20,
    "unattached_disk_days": 30,
    "snapshot_retention_days": 90,
    "image_age_days": 180,
    "abandoned_days": 30,
    "sa_key_max_age_days": 90,
    "gke_request_usage_ratio": 3.0,
    "cold_storage_reads_per_day": 1,
    "ssd_low_iops": 500,
}


class Draft(BaseModel):
    """A rule's output before it becomes a stored recommendation."""
    kind: str  # cost | cleanup | security
    rule: str
    resource_external_id: str
    title: str
    summary: str
    severity: str = "medium"
    current_config: dict[str, Any] = Field(default_factory=dict)
    recommended_config: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    checks: list[dict[str, Any]] = Field(default_factory=list)
    observation_days: int | None = None
    confidence: str = "medium"
    risk: str = "medium"
    impact: str = ""
    procedure: list[str] = Field(default_factory=list)
    action_type: str | None = None
    action_params: dict[str, Any] = Field(default_factory=dict)
    manual_review_reason: str | None = None
    # How savings are worked out: a config to price (resize, storage class), or the full current cost (removal).
    savings_config: dict[str, Any] | None = None
    savings_full: bool = False


def ev(label: str, value: Any, source: str) -> dict[str, Any]:
    return {"label": label, "value": value, "source": source}


def check(name: str, status: str, detail: str) -> dict[str, Any]:
    return {"name": name, "status": status, "detail": detail}  # status: pass | fail | unknown


def age_days(iso: str | None) -> int | None:
    if not iso:
        return None
    return (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).days


def is_prod(env: str) -> bool:
    from .actions import NON_PRODUCTION
    return env.lower() not in NON_PRODUCTION
