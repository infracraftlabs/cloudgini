# Security model

## Principles

- **Read-only by default.** Every account starts with remediation disabled. An admin enables it per account.
- **Least privilege, split duties.** Roles: `viewer` (read, assistant), `analyst` (+ scan, review),
  `operator` (+ remediate), `admin` (+ manage settings and accounts, but **no** remediation).
- **Allow-listed actions only.** Stop a VM, resize a VM within its family, release an unused static
  IP, restrict a firewall rule's source ranges, remove public bucket members. No deletion of data, no
  shell, no arbitrary API calls.
- **No production changes.** Only resources labelled dev, development, test, testing, staging,
  sandbox, demo or qa. Unlabelled counts as production. The check runs at dry-run **and** again at
  execution, and execution also refuses if the resource changed since the dry-run.
- **Destructive means explicit.** Releasing an IP is marked IRREVERSIBLE and needs the resource name typed to approve.
- **Everything audited.** Scans, transitions, dry-runs, approvals, refusals, executions, verifications,
  settings changes and assistant questions are written to an append-only table.

## Credentials

- API keys are random 192-bit values. Only their SHA-256 hashes are configured on the server
  (`CLOUDGINI_API_KEYS`); keys never reach the database, logs or responses.
- The UI keeps the key in an httpOnly, SameSite=Strict cookie and calls the API server-side.
- Cloud access uses Application Default Credentials (the Cloud Run service account; `gcloud auth
  application-default login` locally). CloudGini never reads or stores key files and the database
  has no credential columns.
- Secrets for Cloud Run live in Secret Manager; Terraform creates the secret containers only,
  values are added with `gcloud` so they never enter Terraform state.

## API protections

Bearer-key authentication on every `/api` route, role checks per endpoint, Pydantic validation
with length and range limits, a per-key/IP rate limiter (120/min, 10/min for scan, approve, execute
and assistant), CORS limited to the UI origin, security headers.

## Minimum GCP IAM roles

Read-only (scanning), on each target project:

| Role | Why |
|---|---|
| `roles/cloudasset.viewer` | Resources and IAM policies from Cloud Asset Inventory |
| `roles/compute.viewer` | Machine type sizes; fresh reads for verification |
| `roles/monitoring.viewer` | Utilisation metrics |
| `roles/iam.securityReviewer` | IAM policies and service account key metadata |
| custom: `storage.buckets.get`, `storage.buckets.getIamPolicy` | Fresh bucket policy reads for verification |
| `roles/bigquery.dataViewer` (billing dataset) + `roles/bigquery.jobUser` (host project) | Billing export, optional |
| `roles/securitycenter.findingsViewer` | Security Command Center findings, optional |

Remediation (only where enabled), one custom role with:
`compute.instances.stop`, `compute.instances.start`, `compute.instances.setMachineType`,
`compute.addresses.delete`, `compute.globalAddresses.delete`, `compute.firewalls.update`,
`compute.networks.updatePolicy`, `storage.buckets.setIamPolicy`, and the three
`compute.*Operations.get` permissions. Both are defined in `infra/terraform/cloudrun`.

<!-- REVIEW: confirm compute.firewalls.update also needs compute.networks.updatePolicy for patching source ranges in your org -->

## Assistant

It sees only CloudGini's own analysis, redacted (secrets, tokens, emails) before any model call and
wrapped as data so instructions inside resource names or labels are not followed. It has no tools.
Its answers are explanations; it can't approve or run anything.

## Known gaps

The rate limiter and the simulated estate are per process (run one instance). The backend is
reachable from the internet behind API keys; put it behind IAP or an internal ingress for anything
beyond a demo. There is no SSO or per-user identity yet: an API key is the identity.
