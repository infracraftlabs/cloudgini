# Connecting a GCP project

CloudGini reads a project with Application Default Credentials and only the roles in
[security.md](security.md). Start read-only; enable remediation later, per project, if you want it.

## 1. APIs

```bash
gcloud services enable cloudasset.googleapis.com compute.googleapis.com monitoring.googleapis.com --project PROJECT_ID
```

Optional: `bigquery.googleapis.com` (billing export), `securitycenter.googleapis.com` (SCC findings, if your organisation uses it).

## 2. Identity

- **Cloud Run:** `infra/terraform/cloudrun` creates the `cloudgini-backend` service account and grants the
  read-only roles on every project in `target_project_ids`.
- **Locally:** `gcloud auth application-default login`. CloudGini then runs with *your* permissions, so
  use an account that has only the read-only roles on the demo project, or impersonate the service
  account: `gcloud auth application-default login --impersonate-service-account SA_EMAIL`, where SA_EMAIL is the `backend_service_account` Terraform output.

## 3. Cost data (optional, but needed for any savings figure)

1. In the Cloud Billing console, enable **Detailed usage cost** export to BigQuery (the resource-level
   table, named `gcp_billing_export_resource_v1_…`). Data starts arriving after the export is enabled; it is not backfilled.
2. Grant `roles/bigquery.dataViewer` on the dataset and `roles/bigquery.jobUser` on the host project.
3. Set `CLOUDGINI_GCP_BILLING_TABLE=project.dataset.gcp_billing_export_resource_v1_XXXXXX`.

Without it, the account shows "no billing data" and every savings field says why there is no figure.

## 4. Register and scan

```bash
CLOUDGINI_GCP_PROJECTS=PROJECT_ID   # in .env, or the Cloud Run env
```

Restart the backend. The project appears on **Cloud Accounts** as REAL and read-only. Click **Scan now**.
Errors (API disabled, permission denied) appear on the account row; nothing is half-written.

## 5. Labels CloudGini uses

| Label | Used for |
|---|---|
| `env` or `environment` | Production guard. Only dev, development, test, testing, staging, sandbox, demo, qa can be changed. Missing = production |
| `owner` | Ownership checks. Missing = manual review for cleanup |
| `data-classification` (sensitive, confidential, restricted, pii) | Sensitive-resource checks |
| `retention`, `legal-hold`, `keep` | Blocks automatic cleanup recommendations |

Firewall rules and service accounts have no labels: CloudGini reads `env=… owner=…` from their description.

## 6. Enable remediation (optional)

1. Add the project to `remediation_project_ids` in `infra/terraform/cloudrun` (grants the narrow custom role).
2. On **Cloud Accounts**, an admin clicks **Enable remediation**.
3. Operators can then dry-run, approve and execute the allow-listed actions on non-production resources.
