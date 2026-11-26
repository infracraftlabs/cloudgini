"""Unit tests on the rules engine and the simulated provider (no database)."""
import pytest

from app.engine import cleanup, cost, lifecycle, security
from app.engine.actions import ActionBlocked, build_plan, check_allowed
from app.engine.common import DEFAULT_THRESHOLDS as T
from app.providers.simulated import SimulatedProvider


@pytest.fixture()
def world():
    p = SimulatedProvider()
    res = p.list_resources()
    return p, res, {r.external_id: p.get_resource_metrics(r) for r in res}


def by_name(res, name):
    return next(r for r in res if r.name == name)


def drafts_for(drafts, res, name):
    return [d for d in drafts if d.resource_external_id == by_name(res, name).external_id]


def test_simulated_data_is_labelled(world):
    p, res, metrics = world
    assert res and all(r.data_source == "simulated" for r in res)
    assert all(m.data_source == "simulated" for m in metrics.values() if m)
    from datetime import date, timedelta
    cd = p.get_cost_data(date.today() - timedelta(days=5), date.today())
    assert cd.data_source == "simulated" and cd.basis == "simulated_billing"


def test_missing_metrics_give_manual_review_without_savings(world):
    _, res, metrics = world
    drafts = cost.evaluate(res, metrics, T)
    for name in ("notebook-dev-1", "etl-dev-3"):  # memory metric missing / only 5 days
        [d] = drafts_for(drafts, res, name)
        assert d.manual_review_reason
        assert d.savings_config is None and d.savings_full is False
        assert d.action_type is None


def test_rightsize_and_idle_detected_with_evidence(world):
    _, res, metrics = world
    drafts = cost.evaluate(res, metrics, T)
    [a] = drafts_for(drafts, res, "api-dev-1")
    assert a.rule == "vm_rightsize" and a.recommended_config == {"machine_type": "e2-standard-4"}
    assert a.action_type == "resize_vm" and a.evidence and a.observation_days == 30
    [b] = drafts_for(drafts, res, "batch-dev-2")
    assert b.rule == "vm_idle" and b.action_type == "stop_vm"
    [c] = drafts_for(drafts, res, "web-prod-1")
    assert c.action_type is None  # production: procedure only
    assert not drafts_for(drafts, res, "web-stg-1")  # well utilised


def test_all_ten_security_checks_fire(world):
    _, res, _ = world
    rules = {d.rule for d in security.evaluate(res, T)}
    assert rules == set(security.CHECKS)


def test_cleanup_never_on_age_alone(world):
    _, res, metrics = world
    drafts = cleanup.evaluate(res, metrics, T)
    [scratch] = [d for d in drafts_for(drafts, res, "disk-ml-scratch") if d.rule == "unattached_disk"]
    assert scratch.manual_review_reason and "Backup" in scratch.manual_review_reason
    [old] = drafts_for(drafts, res, "disk-old-data")
    assert old.manual_review_reason is None and all(c["status"] == "pass" for c in old.checks)
    assert not drafts_for(drafts, res, "disk-tmp-restore")  # only 10 days unattached
    [keep] = drafts_for(drafts, res, "snap-ml-baseline")
    assert keep.manual_review_reason and "Retention" in keep.manual_review_reason
    [ip_prod] = drafts_for(drafts, res, "ip-prod-spare")
    assert ip_prod.action_type is None and ip_prod.manual_review_reason


@pytest.mark.parametrize("name,action", [("web-prod-1", "stop_vm"), ("ip-prod-spare", "release_ip"),
                                         ("allow-ssh-all", "restrict_firewall"), ("demo-shop-prod-media", "remove_public_access")])
def test_production_actions_blocked(world, name, action):
    _, res, _ = world
    with pytest.raises(ActionBlocked, match="production|blocked"):
        check_allowed(action, by_name(res, name))


def test_unlabelled_environment_blocked(world):
    _, res, _ = world
    r = by_name(res, "batch-dev-2").model_copy(update={"environment": "unknown"})
    with pytest.raises(ActionBlocked):
        check_allowed("stop_vm", r)


def test_only_allow_listed_actions(world):
    _, res, _ = world
    with pytest.raises(ActionBlocked, match="not an allowed"):
        check_allowed("delete_disk", by_name(res, "disk-old-data"))
    with pytest.raises(ActionBlocked, match="same machine family"):
        build_plan("resize_vm", by_name(res, "api-dev-1"), {"machine_type": "n2-standard-4"})


def test_release_ip_marked_irreversible(world):
    _, res, _ = world
    plan = build_plan("release_ip", by_name(res, "ip-dev-unused"), {})
    assert plan.destructive and not plan.reversible and "IRREVERSIBLE" in plan.rollback


def test_verified_requires_successful_verification():
    with pytest.raises(lifecycle.TransitionError):
        lifecycle.check_system("executed", "verified", verification_ok=False)
    with pytest.raises(lifecycle.TransitionError):
        lifecycle.check_system("executed", "verified", verification_ok=None)
    lifecycle.check_system("executed", "verified", verification_ok=True)
    with pytest.raises(lifecycle.TransitionError):
        lifecycle.check_manual("executed", "verified")  # people can't mark things verified
    with pytest.raises(lifecycle.TransitionError):
        lifecycle.check_manual("detected", "executed")
