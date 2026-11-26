# CloudGini

**Optimize Cloud. Eliminate Waste. Secure Everything.**

CloudGini finds cloud cost savings, unused resources and security misconfigurations, shows the
evidence behind each one, and can fix a small set of them safely: dry-run first, explicit
approval, execution, verification and an audit trail. It runs on a built-in simulated estate out
of the box and can read a real Google Cloud project.

**Status: Prototype.** It works end to end on the simulated provider. The GCP adapter is
experimental: its mapping is tested on recorded-style fixtures but it has not yet been run against
a live project. Not for production use. Part of the [InfraCraft Labs](https://infracraftlabs.com) AI Lab.

## What it does

| Module | What you get |
|---|---|
| Overview | Spend trend, estimated vs verified savings, open findings by severity, recent actions, filters (provider, project, environment, resource type, dates, status) |
| Cost Optimization | VM right-sizing and idle VMs, SSD disk type, Cloud SQL tier, low-traffic load balancers, GKE requests, storage classes. Each has current vs recommended config, utilisation evidence, observation window, savings, confidence, risk and a procedure |
| Resource Cleanup | Unattached disks, unused static IPs, orphaned snapshots, unused load balancers, abandoned dev VMs, old images, unowned resources, with dependency, retention, backup and ownership checks |
| Security | Ten rules-based checks (public buckets, permissive IAM, open SSH/RDP, public databases, encryption, audit logging, old service account keys, broad service account roles, unowned sensitive resources, firewall misconfiguration). Not a compliance assessment |
| Recommendations | One lifecycle for everything: Detected → Reviewed → Approved → Executed → Verified, plus Rejected, Failed and Requires manual review |
| Remediation Center | Five allow-listed, validated actions only: stop or resize a non-production VM, release an unused IP, restrict a firewall rule, remove public bucket access |
| Assistant | Explains CloudGini's own results. Never executes anything. Works without a language model (template answers); uses Claude when `ANTHROPIC_API_KEY` is set |

## Honesty rules built into the code

- Every resource, figure and recommendation is labelled **real** or **simulated**.
- Savings are **estimated** (from billed cost) or **verified** (from billing after the change). Missing metrics or billing data means **no savings figure**, never a guess.
- CloudGini does not delete anything on age or low use alone. A failed or unknown check means **requires manual review**.
- Nothing reaches **Verified** without a successful re-read of the resource.
- Production or unlabelled resources are never changed. Destructive actions say they are irreversible and need typed confirmation.

## Quick start (local, simulated data)

```bash
scripts/init-env.sh           # creates .env (hashes only) and prints four API keys once
docker compose up --build     # PostgreSQL, API on :8000, UI on :3000
```

Open http://localhost:3000 and sign in with the **operator** key. API docs: http://localhost:8000/docs.
Without Docker, see [docs/local-dev.md](docs/local-dev.md).

## Documentation

- [Local development](docs/local-dev.md)
- [Architecture](docs/architecture.md)
- [Security model and IAM roles](docs/security.md)
- [Connecting a GCP project](docs/gcp-setup.md)
- [Demo walkthrough](docs/demo-walkthrough.md)
- [Terraform: demo project and Cloud Run](docs/terraform.md)
- [Known limitations](docs/limitations.md)

## Licence

MIT. See [LICENSE](LICENSE).
