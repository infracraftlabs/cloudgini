# Terraform

Two independent configurations. Neither has been applied yet; run `terraform plan` and read it first.

## `infra/terraform/demo`: planted-issue demo project

Creates the demo estate in a **dedicated, empty** project (you create the project; Terraform refuses
to run unless `confirm_dedicated_demo_project = true`).

```bash
cd infra/terraform/demo
cp terraform.tfvars.example terraform.tfvars   # set project_id
terraform init && terraform plan               # review every resource
python3 ../../../scripts/demo-cost.py --region europe-west1   # price it before applying
terraform apply
```

Resources and the issue each one plants are listed in [demo-walkthrough.md](demo-walkthrough.md).

**Destroy (rollback):** `terraform destroy`. This removes everything it created, including the bucket
(`force_destroy = true`) and the snapshot. Then delete the project if you made it only for this:
`gcloud projects delete PROJECT_ID` (recoverable for 30 days).

If CloudGini changed a resource (stopped a VM, released the IP, narrowed the firewall, removed public
access), `terraform plan` shows the drift; `terraform apply` puts the planted issue back, and
`terraform destroy` still works because a released IP is simply gone already.

## `infra/terraform/cloudrun`: running CloudGini on Cloud Run

Creates Artifact Registry, a `db-f1-micro` Cloud SQL PostgreSQL 16 instance (deletion protection on),
Secret Manager secret containers, two service accounts with the roles in [security.md](security.md),
and two Cloud Run services (backend max 1 instance).

Order of operations:

1. `terraform apply -target=google_artifact_registry_repository.images -target=google_secret_manager_secret.s -target=google_sql_database_instance.db`
2. Build and push the images (or run the `deploy` workflow).
3. Create the database user and add the secret values with `gcloud` (values never enter Terraform state):

   ```bash
   PW=$(openssl rand -hex 24)
   gcloud sql users create cloudgini --instance cloudgini --password "$PW"
   printf 'postgresql+psycopg://cloudgini:%s@/cloudgini?host=/cloudsql/%s' "$PW" "$(terraform output -raw sql_connection_name)" \
     | gcloud secrets versions add cloudgini-database-url --data-file=-
   unset PW
   # API key hashes: generate with scripts/init-env.sh, copy the CLOUDGINI_API_KEYS line value
   gcloud secrets versions add cloudgini-api-keys --data-file=<(grep ^CLOUDGINI_API_KEYS= .env | cut -d= -f2-)
   printf 'unset' | gcloud secrets versions add cloudgini-anthropic-api-key --data-file=-   # "unset" = template answers; or a real key
   ```
4. `terraform apply` for the rest.

**Rollback:** redeploy the previous image tag with `gcloud run deploy … --image …:PREVIOUS_SHA`.
**Destroy:** set `deletion_protection = false` on the SQL instance, apply, then `terraform destroy`.
Export the database first if you want to keep the audit log (`gcloud sql export sql …`).

### GitHub Actions deploy

`.github/workflows/deploy.yml` (manual trigger) uses Workload Identity Federation, so no keys. Set the
repository variables `GCP_PROJECT`, `GCP_REGION`, `GCP_WIF_PROVIDER` and `GCP_DEPLOY_SA`. The deploy
service account needs `roles/run.admin`, `roles/artifactregistry.writer` and `roles/iam.serviceAccountUser`
on the two runtime service accounts.

### Running cost

Not estimated here: it depends on region and traffic. The fixed parts are the Cloud SQL instance and
its storage; Cloud Run scales to zero. Price it in the Google Cloud Pricing Calculator before applying.
