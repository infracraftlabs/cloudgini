"""Scan, recommendation lifecycle and remediation. The API layer only checks roles and calls these."""
from __future__ import annotations

import threading
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from . import audit
from .engine import cleanup, cost, lifecycle, security
from .engine.actions import ACTION_TYPES, ActionBlocked, check_allowed
from .engine.common import DEFAULT_THRESHOLDS, Draft
from .models import Account, Action, CostDaily, Recommendation, Resource, Setting, now
from .providers.base import ActionPlan, ResourceRecord
from .providers.registry import get_provider

_scan_lock = threading.Lock()


class ServiceError(Exception):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


def thresholds(db: Session) -> dict[str, Any]:
    s = db.get(Setting, "thresholds")
    return {**DEFAULT_THRESHOLDS, **(s.value if s else {})}


def to_record(r: Resource) -> ResourceRecord:
    return ResourceRecord(external_id=r.external_id, name=r.name, resource_type=r.resource_type, project=r.project,
                          region=r.region, environment=r.environment, owner=r.owner, labels=r.labels, config=r.config,
                          data_source=r.data_source)


# ---------------------------------------------------------------- scan

def _savings(provider, d: Draft, rec: ResourceRecord, monthly: float | None) -> tuple[float | None, str, str]:
    if d.manual_review_reason and not (d.savings_full or d.savings_config):
        return None, "none", "no savings figure: the evidence is incomplete"
    if not (d.savings_full or d.savings_config):
        return None, "none", "this change doesn't map to a cost line item"
    if monthly is None:
        return None, "none", "no billing data for this resource"
    if d.savings_full:
        return round(monthly, 2), "estimated", "the resource's billed cost over the last 30 days; removing it removes this cost"
    est = provider.estimate_resource_cost(rec, d.savings_config, monthly)
    if est is None:
        return None, "none", "the new configuration couldn't be priced, so no figure is given"
    s = round(monthly - est.monthly, 2)
    if s <= 0:
        return None, "none", "no saving expected"
    return s, "estimated", f"billed {monthly:.2f}/month minus estimated {est.monthly:.2f}/month ({est.method})"


def _next_id(db: Session, kind: str, used: dict[str, int]) -> str:
    if kind not in used:
        used[kind] = db.scalar(select(func.count()).select_from(Recommendation).where(Recommendation.kind == kind)) or 0
    used[kind] += 1
    return f"CG-{kind.upper()}-{used[kind]:04d}"


def scan_account(db: Session, account: Account, actor: str = "system", role: str = "system") -> dict[str, Any]:
    if not _scan_lock.acquire(blocking=False):
        raise ServiceError("a scan is already running")
    try:
        return _scan(db, account, actor, role)
    except ServiceError:
        raise
    except Exception as e:  # report provider failures instead of half-writing results
        db.rollback()
        account.status, account.status_detail = "error", f"{type(e).__name__}: {e}"[:1000]
        audit.record(db, actor, role, "scan", "account", account.id, outcome="failed", error=account.status_detail)
        db.commit()
        raise ServiceError(f"scan failed: {account.status_detail}", 502)
    finally:
        _scan_lock.release()


def _scan(db: Session, account: Account, actor: str, role: str) -> dict[str, Any]:
    p = get_provider(account)
    records = p.list_resources()
    metrics = {r.external_id: p.get_resource_metrics(r) for r in records}
    end = date.today()
    cost_data = p.get_cost_data(end - timedelta(days=59), end)
    last30 = end - timedelta(days=29)
    per_resource: dict[str, float] = defaultdict(float)
    daily: dict[tuple, float] = defaultdict(float)
    for c in cost_data.records:
        if c.resource_external_id and c.day >= last30:
            per_resource[c.resource_external_id] += c.cost
        daily[(c.day, c.service, c.project, c.environment, c.currency)] += c.cost

    existing = {r.external_id: r for r in db.scalars(select(Resource).where(Resource.account_id == account.id))}
    seen = set()
    for rec in records:
        row = existing.get(rec.external_id) or Resource(account_id=account.id, external_id=rec.external_id)
        m = metrics.get(rec.external_id)
        row.name, row.resource_type, row.project, row.region = rec.name, rec.resource_type, rec.project, rec.region
        row.environment, row.owner, row.labels, row.config = rec.environment, rec.owner, rec.labels, rec.config
        row.metrics = m.model_dump() if m else None
        row.monthly_cost = round(per_resource[rec.external_id], 2) if rec.external_id in per_resource else None
        row.cost_basis = cost_data.basis if rec.external_id in per_resource else "none"
        row.data_source, row.last_seen_at = rec.data_source, now()
        db.add(row)
        seen.add(rec.external_id)
    for ext, row in existing.items():
        if ext not in seen:
            db.delete(row)
    db.execute(delete(CostDaily).where(CostDaily.account_id == account.id))
    db.add_all(CostDaily(account_id=account.id, day=k[0], service=k[1], project=k[2], environment=k[3], currency=k[4],
                         cost=round(v, 4), data_source=cost_data.data_source) for k, v in daily.items())
    db.flush()

    t = thresholds(db)
    drafts = cost.evaluate(records, metrics, t) + cleanup.evaluate(records, metrics, t) + p.evaluate_security_rules(records, t)
    for f in p.get_security_findings():
        drafts.append(Draft(kind="security", rule=f"provider:{f.category}", resource_external_id=f.resource_external_id or "",
                            title=f"{f.category} (Security Command Center)", summary=f.description, severity=f.severity.lower(),
                            evidence=[{"label": "Finding", "value": f.external_id, "source": "Security Command Center"}],
                            procedure=["Open the finding in Security Command Center and follow its remediation steps"],
                            manual_review_reason="imported from Security Command Center; review there", confidence="high"))
    rows = {r.external_id: r for r in db.scalars(select(Resource).where(Resource.account_id == account.id))}
    by_ext = {r.external_id: r for r in records}
    used: dict[str, int] = {}
    counts = {"new": 0, "updated": 0, "reopened": 0}
    for d in drafts:
        fp = f"{account.id}|{d.rule}|{d.resource_external_id}"
        rec = db.scalar(select(Recommendation).where(Recommendation.fingerprint == fp))
        res_row = rows.get(d.resource_external_id)
        savings, basis, method = _savings(p, d, by_ext[d.resource_external_id], res_row.monthly_cost) \
            if d.resource_external_id in by_ext and res_row else (None, "none", "resource not in inventory")
        fields = dict(kind=d.kind, rule=d.rule, title=d.title, summary=d.summary, severity=d.severity,
                      current_config=d.current_config, recommended_config=d.recommended_config, evidence=d.evidence,
                      checks=d.checks, observation_days=d.observation_days, confidence=d.confidence, risk=d.risk,
                      impact=d.impact, procedure=d.procedure, action_type=d.action_type, action_params=d.action_params,
                      manual_review_reason=d.manual_review_reason, monthly_savings=savings, savings_basis=basis,
                      savings_method=method, data_source=account.data_source,
                      resource_id=res_row.id if res_row else None)
        if rec is None:
            rec = Recommendation(id=_next_id(db, d.kind, used), fingerprint=fp, account_id=account.id,
                                 state="requires_manual_review" if d.manual_review_reason else "detected", **fields)
            db.add(rec)
            counts["new"] += 1
        elif rec.state in ("detected", "requires_manual_review", "reviewed"):
            for k, v in fields.items():
                setattr(rec, k, v)
            counts["updated"] += 1
        elif rec.state == "verified":
            for k, v in fields.items():
                setattr(rec, k, v)
            rec.state, rec.verification = "detected", None
            audit.record(db, actor, role, "recommendation.reopened", "recommendation", rec.id,
                         outcome="info", reason="the issue was detected again after verification")
            counts["reopened"] += 1
        rec.last_seen_at = now()
    account.status, account.status_detail, account.last_scan_at = "ok", cost_data.note, now()
    summary = {"resources": len(records), "drafts": len(drafts), **counts, "cost_basis": cost_data.basis}
    audit.record(db, actor, role, "scan", "account", account.id, **summary)
    db.commit()
    return summary


# ---------------------------------------------------------------- lifecycle

def transition(db: Session, rec: Recommendation, target: str, actor: str, role: str, note: str | None = None) -> Recommendation:
    try:
        lifecycle.check_manual(rec.state, target)
    except lifecycle.TransitionError as e:
        audit.record(db, actor, role, "recommendation.transition", "recommendation", rec.id, outcome="denied",
                     frm=rec.state, to=target, error=str(e))
        db.commit()
        raise ServiceError(str(e))
    if target == "approved" and rec.action_type:
        raise ServiceError("this recommendation has an automated action: approve it in the Remediation Center (dry-run first)")
    audit.record(db, actor, role, "recommendation.transition", "recommendation", rec.id, frm=rec.state, to=target, note=note)
    rec.state, rec.updated_at = target, now()
    db.commit()
    return rec


def _fresh_resource(db: Session, rec: Recommendation) -> tuple[Any, ResourceRecord | None, Resource | None]:
    account = db.get(Account, rec.account_id)
    p = get_provider(account)
    row = db.get(Resource, rec.resource_id) if rec.resource_id else None
    ext = row.external_id if row else rec.fingerprint.split("|", 2)[2]
    return p, p.get_resource(ext), row


def _rule_still_fires(p, rec: Recommendation, fresh: ResourceRecord | None, t: dict[str, Any]) -> bool:
    if fresh is None:
        return False
    m = {fresh.external_id: p.get_resource_metrics(fresh)}
    drafts = (cost.evaluate([fresh], m, t) + cleanup.evaluate([fresh], m, t) + security.evaluate([fresh], t))
    return any(d.rule == rec.rule for d in drafts)


def mark_manually_executed(db: Session, rec: Recommendation, actor: str, role: str, note: str) -> Recommendation:
    if rec.action_type:
        raise ServiceError("use the Remediation Center for recommendations with an automated action")
    lifecycle.check_system(rec.state, "executed")
    audit.record(db, actor, role, "recommendation.manual_execution", "recommendation", rec.id, note=note)
    rec.state, rec.updated_at = "executed", now()
    db.commit()
    return verify_recommendation(db, rec, actor, role)


def verify_recommendation(db: Session, rec: Recommendation, actor: str, role: str) -> Recommendation:
    """Re-read the resource and re-run the rule. Only a clean result reaches 'verified'."""
    if rec.state != "executed":
        raise ServiceError(f"only executed recommendations can be verified (state is '{rec.state}')")
    p, fresh, _ = _fresh_resource(db, rec)
    fires = _rule_still_fires(p, rec, fresh, thresholds(db))
    result = {"ok": not fires, "checked_at": now().isoformat(),
              "detail": "the rule no longer fires on a fresh read of the resource" if not fires
              else "the rule still fires on a fresh read of the resource"}
    _finish_verification(db, rec, result, actor, role)
    return rec


def _finish_verification(db: Session, rec: Recommendation, result: dict[str, Any], actor: str, role: str) -> None:
    target = "verified" if result["ok"] else "failed"
    lifecycle.check_system(rec.state, target, verification_ok=result["ok"])
    rec.state, rec.verification, rec.updated_at = target, result, now()
    audit.record(db, actor, role, "recommendation.verification", "recommendation", rec.id,
                 outcome="success" if result["ok"] else "failed", **result)
    db.commit()


# ---------------------------------------------------------------- remediation

def _next_action_id(db: Session) -> str:
    n = db.scalar(select(func.count()).select_from(Action)) or 0
    return f"ACT-{n + 1:04d}"


def plan_action(db: Session, rec: Recommendation, actor: str, role: str, params: dict[str, Any] | None = None) -> Action:
    account = db.get(Account, rec.account_id)
    if not rec.action_type:
        raise ServiceError("this recommendation has no automated action; follow its procedure")
    if rec.state != "reviewed":
        raise ServiceError(f"review the recommendation first (state is '{rec.state}', needs 'reviewed')")
    if db.scalar(select(Action).where(Action.recommendation_id == rec.id, Action.state.in_(("planned", "approved")))):
        raise ServiceError("an open action already exists for this recommendation")
    p, fresh, _ = _fresh_resource(db, rec)
    if fresh is None:
        raise ServiceError("the resource no longer exists")
    try:
        plan = p.plan_action(rec.action_type, fresh, {**rec.action_params, **(params or {})})
    except ActionBlocked as e:
        audit.record(db, actor, role, "action.plan", "recommendation", rec.id, outcome="denied", error=str(e))
        db.commit()
        raise ServiceError(str(e), 403)
    act = Action(id=_next_action_id(db), recommendation_id=rec.id, action_type=plan.action_type, params=plan.params,
                 state="planned", plan=plan.model_dump(), reversible=plan.reversible, destructive=plan.destructive,
                 rollback=plan.rollback, requested_by=actor, data_source=account.data_source)
    db.add(act)
    audit.record(db, actor, role, "action.dry_run", "action", act.id, recommendation=rec.id, plan=plan.model_dump())
    db.commit()
    return act


def approve_action(db: Session, act: Action, actor: str, role: str, confirm: str | None) -> Action:
    rec = db.get(Recommendation, act.recommendation_id)
    if act.state != "planned":
        raise ServiceError(f"only planned actions can be approved (state is '{act.state}')")
    if act.destructive:
        name = (db.get(Resource, rec.resource_id).name if rec.resource_id else "")
        if confirm != name:
            audit.record(db, actor, role, "action.approve", "action", act.id, outcome="denied",
                         error="destructive action: confirmation text didn't match the resource name")
            db.commit()
            raise ServiceError(f"this action is IRREVERSIBLE: type the resource name '{name}' to confirm", 400)
    if rec.state != "reviewed":
        raise ServiceError(f"the recommendation must be 'reviewed' to approve its action (state is '{rec.state}')")
    act.state, act.approved_by, act.updated_at = "approved", actor, now()
    rec.state, rec.updated_at = "approved", now()
    audit.record(db, actor, role, "action.approve", "action", act.id, recommendation=rec.id,
                 destructive=act.destructive, reversible=act.reversible)
    db.commit()
    return act


def cancel_action(db: Session, act: Action, actor: str, role: str) -> Action:
    if act.state not in ("planned", "approved"):
        raise ServiceError(f"can't cancel an action in state '{act.state}'")
    rec = db.get(Recommendation, act.recommendation_id)
    if rec.state == "approved":
        rec.state = "reviewed"
    act.state, act.updated_at = "cancelled", now()
    audit.record(db, actor, role, "action.cancel", "action", act.id, recommendation=rec.id)
    db.commit()
    return act


def execute_action(db: Session, act: Action, actor: str, role: str) -> Action:
    rec = db.get(Recommendation, act.recommendation_id)
    account = db.get(Account, rec.account_id)
    if act.state != "approved" or not act.approved_by:
        audit.record(db, actor, role, "action.execute", "action", act.id, outcome="denied", error="not approved")
        db.commit()
        raise ServiceError("the action must be approved before it can run", 403)
    if not account.remediation_enabled:
        audit.record(db, actor, role, "action.execute", "action", act.id, outcome="denied", error="account is read-only")
        db.commit()
        raise ServiceError("remediation is disabled for this account (read-only). An admin can enable it on Cloud Accounts.", 403)
    p, fresh, _ = _fresh_resource(db, rec)
    plan = ActionPlan(**act.plan)
    try:
        if fresh is None:
            raise ActionBlocked("the resource no longer exists")
        check_allowed(act.action_type, fresh)  # labels may have changed since the dry-run
        replanned = p.plan_action(act.action_type, fresh, act.params)
        if replanned.before != plan.before:
            raise ActionBlocked(f"the resource changed since the dry-run (was {plan.before}, now {replanned.before}); plan again")
    except ActionBlocked as e:
        act.state, act.error, act.updated_at = "failed", str(e), now()
        lifecycle.check_system(rec.state, "failed")
        rec.state = "failed"
        audit.record(db, actor, role, "action.execute", "action", act.id, outcome="denied", error=str(e))
        db.commit()
        raise ServiceError(str(e), 403)
    result = p.execute_action(plan)
    act.executed_by, act.result, act.updated_at = actor, result.model_dump(), now()
    if not result.ok:
        act.state, act.error = "failed", result.detail
        rec.state = "failed"
        audit.record(db, actor, role, "action.execute", "action", act.id, outcome="failed", error=result.detail,
                     rollback=act.rollback)
        db.commit()
        return act
    act.state = "executed"
    lifecycle.check_system(rec.state, "executed")
    rec.state = "executed"
    audit.record(db, actor, role, "action.execute", "action", act.id, recommendation=rec.id, result=result.model_dump())
    db.commit()
    return verify_action(db, act, actor, role)


def verify_action(db: Session, act: Action, actor: str, role: str) -> Action:
    rec = db.get(Recommendation, act.recommendation_id)
    if act.state != "executed":
        raise ServiceError(f"only executed actions can be verified (state is '{act.state}')")
    p = get_provider(db.get(Account, rec.account_id))
    v = p.verify_action(ActionPlan(**act.plan))
    act.verification, act.updated_at = v.model_dump(), now()
    act.state = "verified" if v.ok else "failed"
    if not v.ok:
        act.error = f"verification failed: expected {v.expected}, observed {v.observed}. Rollback: {act.rollback}"
    _finish_verification(db, rec, {"ok": v.ok, "expected": v.expected, "observed": v.observed, "detail": v.detail,
                                   "action": act.id, "checked_at": now().isoformat()}, actor, role)
    return act


def action_types() -> dict[str, Any]:
    return ACTION_TYPES
