# Architecture

```
Browser ──> Next.js (UI + /api/proxy) ──> FastAPI ──> PostgreSQL
              API key in httpOnly cookie     │
                                             ├── Rules engine (cost, cleanup, security, lifecycle, actions)
                                             ├── Provider registry ──> SimulatedProvider (synthetic estate)
                                             │                    └──> GcpProvider (Asset Inventory, Monitoring,
                                             │                         BigQuery billing export, SCC, Compute/Storage)
                                             └── Assistant (no tools) ──> Claude, or template answers
```

Simplicity first: two containers and one database, no queues, no workers. Scans run in the request
(one at a time); remediation actions are short API calls.

## Backend layout (`backend/app`)

| Path | Role |
|---|---|
| `providers/base.py` | The four interfaces: `CloudInventoryProvider` (list_resources, get_resource, get_resource_metrics), `CloudCostProvider` (get_cost_data, estimate_resource_cost), `CloudSecurityProvider` (get_security_findings, evaluate_security_rules), `CloudRemediationProvider` (plan_action, execute_action, verify_action) |
| `providers/simulated.py` | 41 synthetic resources across 3 projects with planted issues; synthetic billing and price table; in-memory state that remediation changes |
| `providers/gcp.py` | GCP adapter (experimental). `normalise()` is a pure function, tested on fixtures |
| `providers/registry.py` | Account → provider. AWS and Azure would be one class and one line each |
| `engine/cost.py`, `cleanup.py`, `security.py` | Provider-independent rules over normalised resources. Output: drafts with evidence, checks, procedure |
| `engine/actions.py` | The action allow-list, production guard, dry-run plans and verification comparison |
| `engine/lifecycle.py` | Recommendation state machine: which transitions people may request, which only the system makes |
| `services.py` | Scan (upsert resources, cost, recommendations), transitions, plan/approve/execute/verify |
| `api.py` | REST endpoints, role checks; OpenAPI at `/docs` |
| `security_layer.py` | API keys (hash only), roles, rate limiter |
| `assistant.py` | Builds context from CloudGini's own data, redacts it, asks the model or uses templates |

## Data model

`accounts`, `resources`, `cost_daily`, `recommendations`, `actions`, `audit_events` (append-only),
`settings`. Migrations are in `backend/alembic`. Indexes cover the dashboard filters
(account, type, environment), recommendation kind/state, cost by account and day, and audit time
and target.

## Recommendation lifecycle

```
detected ──> reviewed ──> approved ──> executed ──> verified
   │            │            │            │
   ├──> requires_manual_review            └──> failed ──> reviewed (retry)
   └──> rejected ──> detected (reopen)
```

- People move items between detected, reviewed, rejected and manual review (analyst role) and approve
  procedures (operator).
- For items with an automated action, approval happens on the action after a dry-run.
- `executed` and `verified` are only set by the service. `verified` needs a successful verification:
  a fresh read of the resource compared with the plan (actions) or the rule no longer firing (manual fixes).
- A verified item whose issue is detected again on a later scan is reopened and the audit log says so.

## Savings

`monthly_savings` is one of:
- **estimated**: billed cost of the resource over the last 30 days, minus an estimate of the new
  configuration's cost. The estimate scales the billed cost (simulated: a synthetic price table;
  GCP: vCPU ratio within the same machine family). Removals use the whole billed cost.
- **verified**: reserved for billing data after a change. Not produced yet (see limitations).
- **none**: missing metrics, missing billing data, or a change that can't be priced honestly (GKE
  requests, GCP disk types and storage classes).
