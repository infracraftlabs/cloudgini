"""Integration tests through the REST API on the simulated provider."""
from conftest import auth


def recs(client, **params):
    r = client.get("/api/recommendations", params=params, headers=auth("viewer"))
    assert r.status_code == 200
    return r.json()


def find(client, rule, resource):
    return next(r for r in recs(client, rule=rule) if r["resource_name"] == resource)


def review(client, rec_id):
    r = client.post(f"/api/recommendations/{rec_id}/transition", json={"to": "reviewed"}, headers=auth("analyst"))
    assert r.status_code == 200, r.text


def enable_remediation(client):
    r = client.patch("/api/accounts/sim-demo", json={"remediation_enabled": True}, headers=auth("admin"))
    assert r.status_code == 200


def plan_and_approve(client, rec_id, confirm=None):
    r = client.post(f"/api/recommendations/{rec_id}/actions", json={}, headers=auth("operator"))
    assert r.status_code == 200, r.text
    act = r.json()
    r = client.post(f"/api/actions/{act['id']}/approve", json={"confirm": confirm}, headers=auth("operator"))
    assert r.status_code == 200, r.text
    return act["id"]


def test_auth_and_roles(client):
    assert client.get("/api/overview").status_code == 401
    assert client.get("/api/overview", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.post("/api/accounts/sim-demo/scan", headers=auth("viewer")).status_code == 403
    rec = find(client, "vm_idle", "batch-dev-2")
    # admin manages settings but has no remediation permission
    assert client.post(f"/api/recommendations/{rec['id']}/actions", json={}, headers=auth("admin")).status_code == 403
    assert client.put("/api/settings/thresholds", json={}, headers=auth("operator")).status_code == 403


def test_dashboard_has_labelled_simulated_data(client):
    ov = client.get("/api/overview", headers=auth("viewer")).json()
    assert ov["data_sources"] == ["simulated"]
    assert ov["kpis"]["resources"] > 30 and ov["kpis"]["open_recommendations"] > 20
    assert ov["kpis"]["estimated_monthly_savings"] > 0 and ov["kpis"]["verified_monthly_savings"] == 0
    assert len(ov["cost_trend"]) == 60
    all_recs = recs(client)
    assert all(r["data_source"] == "simulated" for r in all_recs)
    assert all(r["savings_basis"] in ("estimated", "none") for r in all_recs)
    res = client.get("/api/resources", headers=auth("viewer")).json()
    assert all(r["data_source"] == "simulated" for r in res)


def test_missing_metrics_give_no_savings(client):
    r = find(client, "vm_rightsize", "notebook-dev-1")
    assert r["state"] == "requires_manual_review"
    assert r["monthly_savings"] is None and r["savings_basis"] == "none"
    assert find(client, "vm_rightsize", "api-dev-1")["monthly_savings"] > 0


def test_end_to_end_stop_idle_vm(client):
    rec = find(client, "vm_idle", "batch-dev-2")
    review(client, rec["id"])
    act_id = plan_and_approve(client, rec["id"])
    # read-only by default: execution is refused until an admin enables remediation
    r = client.post(f"/api/actions/{act_id}/execute", headers=auth("operator"))
    assert r.status_code == 403 and "read-only" in r.json()["detail"]
    enable_remediation(client)
    r = client.post(f"/api/actions/{act_id}/execute", headers=auth("operator"))
    assert r.status_code == 200 and r.json()["state"] == "verified"
    detail = client.get(f"/api/recommendations/{rec['id']}", headers=auth("viewer")).json()
    assert detail["recommendation"]["state"] == "verified"
    events = [e["event"] for e in detail["audit"]]
    for e in ("recommendation.transition", "action.dry_run", "action.approve", "action.execute", "recommendation.verification"):
        assert e in events
    # re-scan: the VM is stopped, so the recommendation is not reopened
    client.post("/api/accounts/sim-demo/scan", headers=auth("analyst"))
    assert find(client, "vm_idle", "batch-dev-2")["state"] == "verified"


def test_unapproved_action_cannot_execute(client):
    enable_remediation(client)
    rec = find(client, "vm_rightsize", "api-dev-1")
    # not even reviewed: no dry-run allowed
    assert client.post(f"/api/recommendations/{rec['id']}/actions", json={}, headers=auth("operator")).status_code == 409
    review(client, rec["id"])
    act = client.post(f"/api/recommendations/{rec['id']}/actions", json={}, headers=auth("operator")).json()
    r = client.post(f"/api/actions/{act['id']}/execute", headers=auth("operator"))
    assert r.status_code == 403 and "approved" in r.json()["detail"]
    audit = client.get("/api/audit", params={"target_id": act["id"], "outcome": "denied"}, headers=auth("viewer")).json()
    assert audit and audit[0]["event"] == "action.execute"


def test_failed_verification_never_marks_verified(client):
    enable_remediation(client)
    rec = find(client, "firewall_misconfiguration", "allow-all-dev-legacy")
    review(client, rec["id"])
    act_id = plan_and_approve(client, rec["id"])
    act = client.post(f"/api/actions/{act_id}/execute", headers=auth("operator")).json()
    assert act["state"] == "failed" and "verification failed" in act["error"] and act["rollback"]
    detail = client.get(f"/api/recommendations/{rec['id']}", headers=auth("viewer")).json()
    assert detail["recommendation"]["state"] == "failed"
    assert detail["recommendation"]["verification"]["ok"] is False
    # manual path: claiming a fix that wasn't made also fails verification
    db = find(client, "public_database", "reporting-db-dev")
    client.post(f"/api/recommendations/{db['id']}/transition", json={"to": "reviewed"}, headers=auth("analyst"))
    client.post(f"/api/recommendations/{db['id']}/transition", json={"to": "approved"}, headers=auth("operator"))
    r = client.post(f"/api/recommendations/{db['id']}/manual-execution", json={"note": "said it was done"}, headers=auth("operator"))
    assert r.status_code == 200 and r.json()["state"] == "failed"
    # and nobody can set verified by hand
    r = client.post(f"/api/recommendations/{db['id']}/transition", json={"to": "verified"}, headers=auth("operator"))
    assert r.status_code == 422


def test_production_change_blocked_even_after_relabel(client):
    from app.providers.registry import _cache
    enable_remediation(client)
    assert find(client, "vm_rightsize", "web-prod-1")["action_type"] is None
    rec = find(client, "vm_idle", "batch-dev-2")
    review(client, rec["id"])
    act_id = plan_and_approve(client, rec["id"])
    world = _cache["sim-demo"]._world
    vm = next(r for r in world.values() if r.name == "batch-dev-2")
    vm.environment = "prod"  # someone relabels it between approval and execution
    r = client.post(f"/api/actions/{act_id}/execute", headers=auth("operator"))
    assert r.status_code == 403 and "blocked" in r.json()["detail"]
    assert vm.config["status"] == "RUNNING"


def test_irreversible_action_needs_typed_confirmation(client):
    enable_remediation(client)
    rec = find(client, "unused_ip", "ip-dev-unused")
    review(client, rec["id"])
    act = client.post(f"/api/recommendations/{rec['id']}/actions", json={}, headers=auth("operator")).json()
    assert act["destructive"] and not act["reversible"]
    r = client.post(f"/api/actions/{act['id']}/approve", json={}, headers=auth("operator"))
    assert r.status_code == 400 and "IRREVERSIBLE" in r.json()["detail"]
    r = client.post(f"/api/actions/{act['id']}/approve", json={"confirm": "ip-dev-unused"}, headers=auth("operator"))
    assert r.status_code == 200
    assert client.post(f"/api/actions/{act['id']}/execute", headers=auth("operator")).json()["state"] == "verified"


def test_demo_resets_to_clean(client):
    before = {(r["rule"], r["resource_name"], r["state"]) for r in recs(client)}
    enable_remediation(client)
    rec = find(client, "vm_idle", "batch-dev-2")
    review(client, rec["id"])
    client.post(f"/api/actions/{plan_and_approve(client, rec['id'])}/execute", headers=auth("operator"))
    assert client.post("/api/demo/reset", headers=auth("operator")).status_code == 403
    assert client.post("/api/demo/reset", headers=auth("admin")).status_code == 200
    after = {(r["rule"], r["resource_name"], r["state"]) for r in recs(client)}
    assert after == before
    assert client.get("/api/accounts", headers=auth("viewer")).json()[0]["remediation_enabled"] is False
    assert client.get("/api/audit", params={"event": "demo.reset"}, headers=auth("viewer")).json()


def test_assistant_works_without_llm(client):
    r = client.post("/api/assistant", json={"question": "What should I fix first?"}, headers=auth("viewer"))
    assert r.status_code == 200 and r.json()["mode"] == "template" and "estimated" in r.json()["answer"].lower()
    rec = find(client, "vm_rightsize", "notebook-dev-1")
    a = client.post("/api/assistant", json={"question": "Why no savings?", "recommendation_id": rec["id"]},
                    headers=auth("viewer")).json()["answer"]
    assert "No savings figure" in a


def test_validation_and_rate_limit(client):
    from app.config import get_settings
    assert client.post("/api/assistant", json={"question": ""}, headers=auth("viewer")).status_code == 422
    s = get_settings()
    old = s.rate_limit_per_minute
    s.rate_limit_per_minute = 3
    try:
        codes = [client.get("/api/me", headers={"Authorization": "Bearer rate-limit-probe"}).status_code for _ in range(5)]
    finally:
        s.rate_limit_per_minute = old
    assert codes[:3] == [401] * 3 and codes[3:] == [429, 429]


def test_no_credentials_in_responses(client):
    import json
    from conftest import KEYS
    body = json.dumps([client.get(u, headers=auth("viewer")).json() for u in
                       ("/api/accounts", "/api/settings", "/api/resources", "/api/audit")])
    assert not any(k in body for k in KEYS.values())
    assert "sha256" not in body.lower() and "api_keys" not in body
