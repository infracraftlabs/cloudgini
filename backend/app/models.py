"""Database tables. Credentials are never stored: real accounts use the runtime's
Application Default Credentials (a service account on Cloud Run, `gcloud auth` locally)."""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(16))  # simulated | gcp | aws | azure
    name: Mapped[str] = mapped_column(String(128))
    scope_id: Mapped[str] = mapped_column(String(128))  # GCP project ID
    data_source: Mapped[str] = mapped_column(String(16))  # real | simulated
    remediation_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default="never_scanned")
    status_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Resource(Base):
    __tablename__ = "resources"
    __table_args__ = (
        UniqueConstraint("account_id", "external_id", name="uq_resource_external"),
        Index("ix_resources_filters", "account_id", "resource_type", "environment"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    external_id: Mapped[str] = mapped_column(String(512))
    name: Mapped[str] = mapped_column(String(256))
    resource_type: Mapped[str] = mapped_column(String(64))
    project: Mapped[str] = mapped_column(String(128))
    region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    environment: Mapped[str] = mapped_column(String(32), default="unknown")
    owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    labels: Mapped[dict] = mapped_column(JSON, default=dict)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    monthly_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_basis: Mapped[str] = mapped_column(String(32), default="none")
    data_source: Mapped[str] = mapped_column(String(16))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CostDaily(Base):
    __tablename__ = "cost_daily"
    __table_args__ = (Index("ix_cost_daily_account_day", "account_id", "day"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    day: Mapped[date] = mapped_column(Date)
    service: Mapped[str] = mapped_column(String(128))
    project: Mapped[str] = mapped_column(String(128))
    environment: Mapped[str] = mapped_column(String(32))
    cost: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    data_source: Mapped[str] = mapped_column(String(16))


class Recommendation(Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        UniqueConstraint("fingerprint", name="uq_recommendation_fingerprint"),
        Index("ix_recommendations_kind_state", "kind", "state"),
        Index("ix_recommendations_account", "account_id"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # e.g. CG-COST-0007
    fingerprint: Mapped[str] = mapped_column(String(256))  # account|rule|resource
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    resource_id: Mapped[int | None] = mapped_column(ForeignKey("resources.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String(16))  # cost | cleanup | security
    rule: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(256))
    summary: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(16))  # critical | high | medium | low | info
    state: Mapped[str] = mapped_column(String(32), default="detected")
    current_config: Mapped[dict] = mapped_column(JSON, default=dict)
    recommended_config: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    checks: Mapped[list] = mapped_column(JSON, default=list)  # dependency / retention / backup checks
    observation_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    monthly_savings: Mapped[float | None] = mapped_column(Float, nullable=True)
    savings_basis: Mapped[str] = mapped_column(String(16), default="none")  # estimated | verified | none
    savings_method: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[str] = mapped_column(String(16), default="low")
    risk: Mapped[str] = mapped_column(String(16), default="medium")
    impact: Mapped[str] = mapped_column(Text, default="")
    procedure: Mapped[list] = mapped_column(JSON, default=list)
    action_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    action_params: Mapped[dict] = mapped_column(JSON, default=dict)
    manual_review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    data_source: Mapped[str] = mapped_column(String(16))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Action(Base):
    __tablename__ = "actions"
    __table_args__ = (Index("ix_actions_recommendation", "recommendation_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # ACT-0001
    recommendation_id: Mapped[str] = mapped_column(ForeignKey("recommendations.id", ondelete="CASCADE"))
    action_type: Mapped[str] = mapped_column(String(32))
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    state: Mapped[str] = mapped_column(String(16))  # planned | approved | executed | verified | failed | cancelled
    plan: Mapped[dict] = mapped_column(JSON, default=dict)  # dry-run output
    reversible: Mapped[bool] = mapped_column(Boolean, default=True)
    destructive: Mapped[bool] = mapped_column(Boolean, default=False)
    rollback: Mapped[str] = mapped_column(Text, default="")
    requested_by: Mapped[str] = mapped_column(String(64))
    approved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    executed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    verification: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_source: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuditEvent(Base):
    """Append-only: the API has no update or delete for this table."""
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_ts", "ts"), Index("ix_audit_target", "target_type", "target_id"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    actor: Mapped[str] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(16))
    event: Mapped[str] = mapped_column(String(64))
    target_type: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[str] = mapped_column(String(64))
    outcome: Mapped[str] = mapped_column(String(16))  # success | denied | failed | info
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)
    updated_by: Mapped[str] = mapped_column(String(64), default="system")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
