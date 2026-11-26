from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from . import assistant, audit, services
from .db import get_db
from .engine.actions import ACTION_TYPES
from .engine.common import DEFAULT_THRESHOLDS
from .engine.lifecycle import MANUAL_TRANSITIONS, STATES
from .engine.security import CHECKS
from .models import Account, Action, AuditEvent, CostDaily, Recommendation, Resource, Setting, now
from .schemas import (AccountOut, AccountPatch, ActionOut, ApproveIn, AssistantIn, AuditOut, Filters, NoteIn, PlanIn,
                      RecommendationOut, ResourceOut, ThresholdsIn, TransitionIn)
from .security_layer import PERMISSIONS, Principal, current_principal, require

router = APIRouter(prefix="/api")
DB = Annotated[Session, Depends(get_db)]
F = Annotated[Filters, Query()]
OPEN = ("detected", "reviewed", "approved", "executed", "failed", "requires_manual_review")


def _err(e: services.ServiceError):
    raise HTTPException(e.status, str(e))


def _get(db: Session, model, id_: Any, what: str):
    obj = db.get(model, id_)
    if obj is None:
        raise HTTPException(404, f"{what} not found")
    return obj


# ---------------------------------------------------------------- identity, accounts

@router.get("/me")
def me(p: Principal = Depends(current_principal)) -> dict[str, Any]:
    return {"name": p.name, "role": p.role, "permissions": sorted(PERMISSIONS[p.role])}


@router.get("/accounts", response_model=list[AccountOut])
def list_accounts(db: DB, p: Principal = Depends(require("read"))):
    return db.scalars(select(Account).order_by(Account.created_at)).all()


@router.patch("/accounts/{account_id}", response_model=AccountOut)
def patch_account(account_id: str, body: AccountPatch, db: DB, p: Principal = Depends(require("manage"))):
    a = _get(db, Account, account_id, "account")
    audit.record(db, p.name, p.role, "account.remediation_toggle", "account", a.id,
                 frm=a.remediation_enabled, to=body.remediation_enabled)
    a.remediation_enabled = body.remediation_enabled
    db.commit()
    return a


@router.post("/accounts/{account_id}/scan")
def scan(account_id: str, db: DB, p: Principal = Depends(require("scan"))):
    try:
        return services.scan_account(db, _get(db, Account, account_id, "account"), p.name, p.role)
    except services.ServiceError as e:
        _err(e)


@router.post("/demo/reset")
def demo_reset(db: DB, p: Principal = Depends(require("manage"))):
    """Restore every simulated account to its initial state and re-scan. Real accounts are untouched.
    The audit log is append-only and is kept (the reset itself is recorded)."""
    from .providers.registry import get_provider
    out = {}
    for a in db.scalars(select(Account).where(Account.provider == "simulated")):
        rec_ids = list(db.scalars(select(Recommendation.id).where(Recommendation.account_id == a.id)))
        if rec_ids:
            for act in db.scalars(select(Action).where(Action.recommendation_id.in_(rec_ids))):
                db.delete(act)
        for model in (Recommendation, Resource, CostDaily):
            for row in db.scalars(select(model).where(model.account_id == a.id)):
                db.delete(row)
        a.remediation_enabled = False
        get_provider(a).reset()
        audit.record(db, p.name, p.role, "demo.reset", "account", a.id)
        db.commit()
        out[a.id] = services.scan_account(db, a, p.name, p.role)
    return out


# ---------------------------------------------------------------- read models

def _rec_query(f: Filters, kind: str | None = None) -> Select:
    q = select(Recommendation, Resource, Account).join(Account, Recommendation.account_id == Account.id) \
        .outerjoin(Resource, Recommendation.resource_id == Resource.id)
    if kind:
        q = q.where(Recommendation.kind == kind)
    if f.provider:
        q = q.where(Account.provider == f.provider)
    if f.account_id:
        q = q.where(Account.id == f.account_id)
    if f.project:
        q = q.where(Resource.project == f.project)
    if f.environment:
        q = q.where(Resource.environment == f.environment)
    if f.resource_type:
        q = q.where(Resource.resource_type == f.resource_type)
    if f.state == "open":
        q = q.where(Recommendation.state.in_(OPEN))
    elif f.state:
        q = q.where(Recommendation.state == f.state)
    if f.date_from:
        q = q.where(Recommendation.detected_at >= f.date_from)
    if f.date_to:
        q = q.where(Recommendation.detected_at < f.date_to + timedelta(days=1))
    return q


def _rec_out(rec: Recommendation, res: Resource | None, acc: Account) -> dict[str, Any]:
    d = RecommendationOut.model_validate(rec).model_dump()
    d.update(resource_name=res.name if res else None, resource_type=res.resource_type if res else None,
             project=res.project if res else None, environment=res.environment if res else None, provider=acc.provider)
    return d


SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


@router.get("/recommendations", response_model=list[RecommendationOut])
def list_recommendations(db: DB, f: F, kind: str | None = None, severity: str | None = None, rule: str | None = None,
                         p: Principal = Depends(require("read"))):
    q = _rec_query(f, kind)
    if severity:
        q = q.where(Recommendation.severity == severity)
    if rule:
        q = q.where(Recommendation.rule == rule)
    rows = [_rec_out(*r) for r in db.execute(q).all()]
    return sorted(rows, key=lambda r: (SEV_ORDER.get(r["severity"], 9), -(r["monthly_savings"] or 0), r["id"]))


@router.get("/recommendations/{rec_id}")
def get_recommendation(rec_id: str, db: DB, p: Principal = Depends(require("read"))) -> dict[str, Any]:
    rec = _get(db, Recommendation, rec_id, "recommendation")
    res = db.get(Resource, rec.resource_id) if rec.resource_id else None
    acc = db.get(Account, rec.account_id)
    acts = db.scalars(select(Action).where(Action.recommendation_id == rec.id).order_by(Action.created_at)).all()
    ids = [rec.id] + [a.id for a in acts]
    events = db.scalars(select(AuditEvent).where(AuditEvent.target_id.in_(ids)).order_by(AuditEvent.id)).all()
    return {"recommendation": _rec_out(rec, res, acc),
            "resource": ResourceOut.model_validate(res).model_dump() if res else None,
            "account": AccountOut.model_validate(acc).model_dump(),
            "actions": [ActionOut.model_validate(a).model_dump() for a in acts],
            "audit": [AuditOut.model_validate(e).model_dump() for e in events],
            "allowed_transitions": sorted(MANUAL_TRANSITIONS.get(rec.state, set()) - ({"approved"} if rec.action_type else set()))}


@router.post("/recommendations/{rec_id}/transition", response_model=RecommendationOut)
def transition(rec_id: str, body: TransitionIn, db: DB, p: Principal = Depends(current_principal)):
    perm = "remediate" if body.to == "approved" else "review"
    if not p.can(perm):
        raise HTTPException(403, f"role '{p.role}' lacks the '{perm}' permission")
    rec = _get(db, Recommendation, rec_id, "recommendation")
    try:
        services.transition(db, rec, body.to, p.name, p.role, body.note)
    except services.ServiceError as e:
        _err(e)
    return _rec_out(rec, db.get(Resource, rec.resource_id) if rec.resource_id else None, db.get(Account, rec.account_id))


@router.post("/recommendations/{rec_id}/manual-execution", response_model=RecommendationOut)
def manual_execution(rec_id: str, body: NoteIn, db: DB, p: Principal = Depends(require("remediate"))):
    """Record that a person carried out the procedure; CloudGini then verifies it on a fresh read."""
    rec = _get(db, Recommendation, rec_id, "recommendation")
    try:
        services.mark_manually_executed(db, rec, p.name, p.role, body.note)
    except (services.ServiceError,) as e:
        _err(e)
    except Exception as e:  # lifecycle.TransitionError
        raise HTTPException(409, str(e))
    return _rec_out(rec, db.get(Resource, rec.resource_id) if rec.resource_id else None, db.get(Account, rec.account_id))


@router.post("/recommendations/{rec_id}/verify", response_model=RecommendationOut)
def verify_recommendation(rec_id: str, db: DB, p: Principal = Depends(require("remediate"))):
    rec = _get(db, Recommendation, rec_id, "recommendation")
    try:
        services.verify_recommendation(db, rec, p.name, p.role)
    except services.ServiceError as e:
        _err(e)
    return _rec_out(rec, db.get(Resource, rec.resource_id) if rec.resource_id else None, db.get(Account, rec.account_id))


@router.get("/resources", response_model=list[ResourceOut])
def list_resources(db: DB, f: F, p: Principal = Depends(require("read"))):
    q = select(Resource).join(Account)
    for col, val in ((Account.provider, f.provider), (Account.id, f.account_id), (Resource.project, f.project),
                     (Resource.environment, f.environment), (Resource.resource_type, f.resource_type)):
        if val:
            q = q.where(col == val)
    return db.scalars(q.order_by(Resource.project, Resource.name)).all()


@router.get("/filters")
def filters(db: DB, p: Principal = Depends(require("read"))) -> dict[str, list[str]]:
    def distinct(col):
        return sorted(v for v in db.scalars(select(col).distinct()) if v)
    return {"provider": distinct(Account.provider), "account_id": distinct(Account.id), "project": distinct(Resource.project),
            "environment": distinct(Resource.environment), "resource_type": distinct(Resource.resource_type),
            "state": STATES}


@router.get("/overview")
def overview(db: DB, f: F, p: Principal = Depends(require("read"))) -> dict[str, Any]:
    rows = db.execute(_rec_query(f)).all()
    recs = [r[0] for r in rows]
    open_ = [r for r in recs if r.state in OPEN]
    accounts = db.scalars(select(Account)).all()
    acc_ids = [a.id for a in accounts if (not f.provider or a.provider == f.provider) and (not f.account_id or a.id == f.account_id)]
    rq = select(Resource).where(Resource.account_id.in_(acc_ids))
    for col, val in ((Resource.project, f.project), (Resource.environment, f.environment), (Resource.resource_type, f.resource_type)):
        if val:
            rq = rq.where(col == val)
    resources = db.scalars(rq).all()
    end = f.date_to or date.today()
    start = f.date_from or end - timedelta(days=59)
    cq = select(CostDaily).where(CostDaily.account_id.in_(acc_ids), CostDaily.day >= start, CostDaily.day <= end)
    if f.project:
        cq = cq.where(CostDaily.project == f.project)
    if f.environment:
        cq = cq.where(CostDaily.environment == f.environment)
    costs = db.scalars(cq).all()
    trend: dict[str, float] = defaultdict(float)
    by_service: dict[str, float] = defaultdict(float)
    last30 = end - timedelta(days=29)
    for c in costs:
        trend[c.day.isoformat()] += c.cost
        if c.day >= last30:
            by_service[c.service] += c.cost
    sev = defaultdict(int)
    for r in open_:
        if r.kind == "security":
            sev[r.severity] += 1
    states = defaultdict(int)
    for r in recs:
        states[r.state] += 1
    savings_kind: dict[str, float] = defaultdict(float)
    for r in open_:
        if r.monthly_savings and r.savings_basis == "estimated":
            savings_kind[r.kind] += r.monthly_savings
    events = db.scalars(select(AuditEvent).where(AuditEvent.event.like("action.%") | AuditEvent.event.like("recommendation.%"))
                        .order_by(AuditEvent.id.desc()).limit(8)).all()
    sources = sorted({a.data_source for a in accounts if a.id in acc_ids and a.last_scan_at})
    return {
        "data_sources": sources,
        "kpis": {
            "resources": len(resources),
            "monthly_cost_30d": round(sum(by_service.values()), 2),
            "cost_basis": sorted({r.cost_basis for r in resources if r.cost_basis != "none"}),
            "estimated_monthly_savings": round(sum(r.monthly_savings or 0 for r in open_ if r.savings_basis == "estimated"), 2),
            "verified_monthly_savings": round(sum(r.monthly_savings or 0 for r in recs if r.savings_basis == "verified"), 2),
            "recommendations_without_savings_figure": sum(1 for r in open_ if r.kind != "security" and r.monthly_savings is None),
            "open_recommendations": len(open_),
            "security_open": sum(1 for r in open_ if r.kind == "security"),
            "critical_high_open": sum(1 for r in open_ if r.kind == "security" and r.severity in ("critical", "high")),
            "cleanup_candidates": sum(1 for r in open_ if r.kind == "cleanup"),
            "manual_review": sum(1 for r in recs if r.state == "requires_manual_review"),
            "verified": sum(1 for r in recs if r.state == "verified"),
            "data_sources": sources,
        },
        "cost_trend": [{"day": d, "cost": round(v, 2)} for d, v in sorted(trend.items())],
        "cost_by_service": sorted(({"service": k, "cost": round(v, 2)} for k, v in by_service.items()), key=lambda x: -x["cost"]),
        "severity_breakdown": [{"severity": s, "count": sev.get(s, 0)} for s in ("critical", "high", "medium", "low", "info")],
        "state_breakdown": [{"state": s, "count": states.get(s, 0)} for s in STATES],
        "savings_by_kind": [{"kind": k, "estimated": round(v, 2)} for k, v in sorted(savings_kind.items())],
        "recent_activity": [AuditOut.model_validate(e).model_dump() for e in events],
    }


@router.get("/security/checks")
def security_checks(db: DB, f: F, p: Principal = Depends(require("read"))) -> list[dict[str, Any]]:
    recs = [r[0] for r in db.execute(_rec_query(f, "security")).all()]
    out = []
    for key, name in CHECKS.items():
        mine = [r for r in recs if r.rule == key]
        out.append({"rule": key, "name": name, "open": sum(1 for r in mine if r.state in OPEN),
                    "resolved": sum(1 for r in mine if r.state == "verified"), "total": len(mine)})
    return out


# ---------------------------------------------------------------- remediation

@router.get("/action-types")
def action_types(p: Principal = Depends(require("read"))) -> dict[str, Any]:
    return ACTION_TYPES


@router.post("/recommendations/{rec_id}/actions", response_model=ActionOut)
def plan(rec_id: str, body: PlanIn, db: DB, p: Principal = Depends(require("remediate"))):
    """Dry-run: works out exactly what would change. Nothing is changed in the cloud."""
    try:
        return services.plan_action(db, _get(db, Recommendation, rec_id, "recommendation"), p.name, p.role, body.params())
    except services.ServiceError as e:
        _err(e)


@router.get("/actions", response_model=list[ActionOut])
def list_actions(db: DB, state: str | None = None, p: Principal = Depends(require("read"))):
    q = select(Action).order_by(Action.created_at.desc())
    if state:
        q = q.where(Action.state == state)
    return db.scalars(q).all()


@router.get("/actions/{action_id}", response_model=ActionOut)
def get_action(action_id: str, db: DB, p: Principal = Depends(require("read"))):
    return _get(db, Action, action_id, "action")


def _act(fn, action_id: str, db: Session, p: Principal, *args):
    try:
        return fn(db, _get(db, Action, action_id, "action"), p.name, p.role, *args)
    except services.ServiceError as e:
        _err(e)


@router.post("/actions/{action_id}/approve", response_model=ActionOut)
def approve(action_id: str, body: ApproveIn, db: DB, p: Principal = Depends(require("remediate"))):
    return _act(services.approve_action, action_id, db, p, body.confirm)


@router.post("/actions/{action_id}/execute", response_model=ActionOut)
def execute(action_id: str, db: DB, p: Principal = Depends(require("remediate"))):
    return _act(services.execute_action, action_id, db, p)


@router.post("/actions/{action_id}/verify", response_model=ActionOut)
def verify(action_id: str, db: DB, p: Principal = Depends(require("remediate"))):
    return _act(services.verify_action, action_id, db, p)


@router.post("/actions/{action_id}/cancel", response_model=ActionOut)
def cancel(action_id: str, db: DB, p: Principal = Depends(require("remediate"))):
    return _act(services.cancel_action, action_id, db, p)


# ---------------------------------------------------------------- audit, settings, assistant

@router.get("/audit", response_model=list[AuditOut])
def list_audit(db: DB, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
               event: str | None = None, target_id: str | None = None, outcome: str | None = None,
               p: Principal = Depends(require("read"))):
    q = select(AuditEvent).order_by(AuditEvent.id.desc())
    if event:
        q = q.where(AuditEvent.event.like(f"{event}%"))
    if target_id:
        q = q.where(AuditEvent.target_id == target_id)
    if outcome:
        q = q.where(AuditEvent.outcome == outcome)
    return db.scalars(q.offset(offset).limit(limit)).all()


@router.get("/settings")
def get_settings_(db: DB, p: Principal = Depends(require("read"))) -> dict[str, Any]:
    from .config import get_settings
    s = get_settings()
    return {"thresholds": services.thresholds(db), "defaults": DEFAULT_THRESHOLDS, "assistant": assistant.llm_status(),
            "rate_limit_per_minute": s.rate_limit_per_minute,
            "sensitive_rate_limit_per_minute": s.sensitive_rate_limit_per_minute,
            "gcp_billing_table_configured": bool(s.gcp_billing_table),
            "roles": {k: sorted(v) for k, v in PERMISSIONS.items()}}


@router.put("/settings/thresholds")
def put_thresholds(body: ThresholdsIn, db: DB, p: Principal = Depends(require("manage"))) -> dict[str, Any]:
    row = db.get(Setting, "thresholds") or Setting(key="thresholds", value={})
    audit.record(db, p.name, p.role, "settings.thresholds", "settings", "thresholds", frm=row.value, to=body.model_dump())
    row.value, row.updated_by, row.updated_at = body.model_dump(), p.name, now()
    db.add(row)
    db.commit()
    return {"thresholds": services.thresholds(db), "note": "applies from the next scan"}


@router.post("/assistant")
def ask(body: AssistantIn, db: DB, p: Principal = Depends(require("assistant"))) -> dict[str, Any]:
    ctx: dict[str, Any] = {}
    if body.recommendation_id:
        rec = _get(db, Recommendation, body.recommendation_id, "recommendation")
        ctx["focus"] = _rec_out(rec, db.get(Resource, rec.resource_id) if rec.resource_id else None, db.get(Account, rec.account_id))
    else:
        ov = overview(db, Filters(), p)
        ctx["kpis"] = ov["kpis"]
        ctx["recommendations"] = [_rec_out(*r) for r in db.execute(_rec_query(Filters(state="open"))).all()]
    out = assistant.answer(body.question, ctx)
    audit.record(db, p.name, p.role, "assistant.question", "recommendation" if body.recommendation_id else "overview",
                 body.recommendation_id or "-", outcome="info", mode=out["mode"], redactions=out["redactions"])
    db.commit()
    return out
