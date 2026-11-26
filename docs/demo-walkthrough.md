# Demo walkthrough

## Part 1: simulated estate (no cloud account, about 10 minutes)

Start the app ([local-dev.md](local-dev.md)) and sign in with the **operator** key. Everything you see
is labelled SIMULATED. Prices come from a synthetic table and are not real cloud prices.

1. **Overview.** About 41 resources in 3 projects, roughly 37 open items, 15 open security findings.
   The "estimated savings" KPI counts only items with evidence; "no figure" items are counted separately.
2. **Cost Optimization → VMs.**
   - `api-dev-1` (e2-standard-8, CPU p95 12%, memory p95 28%, 30 days): downsize to e2-standard-4, with a savings estimate.
   - `notebook-dev-1`: memory metric missing → **requires manual review, no figure**.
   - `etl-dev-3`: only 5 days of metrics → **requires manual review, no figure**.
   - `web-prod-1`: a recommendation, but production → procedure only, no automated action.
3. **Resource Cleanup.** Compare `disk-old-data` (all checks pass, recent snapshot) with
   `disk-ml-scratch` (no backup, no owner → manual review). `disk-tmp-restore` (10 days) isn't listed.
4. **Security.** All ten checks have at least one finding; open a public bucket to see evidence,
   impact and the remediation procedure.
5. **Approve → execute → verify (success).** Open `Stop idle VM batch-dev-2` → *Mark reviewed* →
   *Run dry-run*. In the Remediation Center, read the plan (steps, before/after, preconditions,
   rollback), *Approve*, *Execute… → Confirm*. The account is read-only at first, so execution is
   **refused** (shown and audited). Sign in as **admin**, enable remediation on Cloud Accounts, sign back
   in as operator and execute. The action ends **verified**; the recommendation shows the verification.
6. **Failed verification.** Do the same for `Firewall rule allow-all-dev-legacy…`. The simulated estate
   has another tool re-apply the old rule, so verification sees `0.0.0.0/0` still there: the action and
   the recommendation end **failed**, with the rollback text. Nothing is marked verified.
7. **Irreversible action.** `Unused static IP ip-dev-unused` → review → dry-run. Approval needs the
   name typed in; the plan says IRREVERSIBLE.
8. **Manual fix.** Approve `Cloud SQL reporting-db-dev accepts connections from anywhere` and click
   *Record as done*. Nothing was changed, so verification fails: CloudGini doesn't take your word for it.
9. **Audit History.** Every step above, including refusals, with who did it.
10. **Assistant.** *Ask CloudGini* on any page, or *Explain* on a recommendation. Without
    `ANTHROPIC_API_KEY` the answers are templates built from the same data.
11. **Repeat from clean.** Admin → Cloud Accounts → *Reset simulated demo*. Recommendations, actions
    and the estate return to their initial state; the audit log keeps the history.

## Part 2: real GCP demo project (optional, billable)

`infra/terraform/demo` builds a small estate with planted issues in a dedicated project. **It costs
money while it runs.** Price it first with `scripts/demo-cost.py` (Google's list prices from the
Cloud Billing Catalog API) and confirm in the Pricing Calculator; destroy it when you're done.

### What it creates

| Resource | Planted issue | Expected in CloudGini | When |
|---|---|---|---|
| `cg-demo-oversized` e2-standard-4, idle | oversized | VM right-size to e2-standard-2 (action: resize) | after 14 days of CPU+memory metrics (7 if you lower *min observation days* in Settings). Before that: manual review, no figure |
| `cg-demo-underused` e2-standard-2, idle | underused | Stop idle VM (action: stop) | same as above |
| `cg-demo-big-ssd` 100 GB pd-ssd, attached, almost no I/O | big disk | Move to pd-balanced; **no savings figure on GCP** (no list-price guessing) | after the metrics window |
| `cg-demo-unattached` 50 GB pd-standard | unattached disk | Unattached disk candidate | after 30 days (7 at the lowest setting) |
| `cg-demo-unused-ip` | unused IP | Unused static IP (action: release, irreversible) | first scan |
| `cg-demo-old-snapshot` | old snapshot | Listed in inventory only. It becomes an *orphaned snapshot* candidate only once its source disk is gone **and** it is older than the retention threshold (default 90 days). CloudGini can't make a snapshot look old | later |
| `PROJECT-cg-demo-public` bucket with `allUsers` | public bucket | Public bucket, high (action: remove public access) | first scan |
| `cg-demo-overprivileged` SA with Editor | permissive IAM | Broad primitive roles + service account with Editor | first scan |
| `cg-demo-open-ssh` 0.0.0.0/0 tcp:22 | open SSH | SSH open to the internet (action: restrict to the IAP range) | first scan |
| project audit config | data access logs off (default) | Data access audit logs off | first scan |

Also expect findings you didn't plant: for example your own `user:` Owner binding, or the default
Compute Engine service account's Editor role if your organisation still grants it. They are real.

Savings figures appear only if the detailed billing export is configured and has data for these
resources (export data is not backfilled).

### Steps

1. Create a new project and link billing. Do not reuse a project with anything else in it.
2. `infra/terraform/demo`: set `project_id` and `confirm_dedicated_demo_project = true`, `terraform plan`, then apply.
3. Set `CLOUDGINI_GCP_PROJECTS=<project>` and restart the backend; scan from Cloud Accounts.
4. Walk through the same flow as Part 1 on REAL data. For actions, enable remediation (Terraform role + admin toggle).

### Cleanup

```bash
cd infra/terraform/demo && terraform destroy
gcloud projects delete PROJECT_ID   # if the project was only for this demo
```

Then remove the project from `CLOUDGINI_GCP_PROJECTS`. Its account row and audit history stay in
CloudGini's database.
