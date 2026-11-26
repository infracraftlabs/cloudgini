locals {
  apis = ["run.googleapis.com", "artifactregistry.googleapis.com", "sqladmin.googleapis.com",
  "secretmanager.googleapis.com", "cloudasset.googleapis.com", "monitoring.googleapis.com", "bigquery.googleapis.com"]
  read_roles  = ["roles/cloudasset.viewer", "roles/compute.viewer", "roles/monitoring.viewer", "roles/iam.securityReviewer"]
  read_grants = { for pair in setproduct(var.target_project_ids, local.read_roles) : "${pair[0]}|${pair[1]}" => pair }
}

resource "google_project_service" "apis" {
  for_each           = toset(local.apis)
  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "images" {
  repository_id = "cloudgini"
  location      = var.region
  format        = "DOCKER"
  depends_on    = [google_project_service.apis]
}

# ---------------------------------------------------------------- identity
resource "google_service_account" "backend" {
  account_id   = "cloudgini-backend"
  display_name = "CloudGini backend (read-only unless remediation_project_ids is set)"
}

resource "google_service_account" "frontend" {
  account_id   = "cloudgini-frontend"
  display_name = "CloudGini frontend (no cloud permissions)"
}

resource "google_project_iam_member" "read" {
  for_each = local.read_grants
  project  = each.value[0]
  role     = each.value[1]
  member   = "serviceAccount:${google_service_account.backend.email}"
}

resource "google_project_iam_custom_role" "bucket_policy_reader" {
  for_each    = toset(var.target_project_ids)
  project     = each.value
  role_id     = "cloudginiBucketPolicyReader"
  title       = "CloudGini bucket policy reader"
  permissions = ["storage.buckets.get", "storage.buckets.getIamPolicy"]
}

resource "google_project_iam_member" "bucket_policy_reader" {
  for_each = toset(var.target_project_ids)
  project  = each.value
  role     = google_project_iam_custom_role.bucket_policy_reader[each.value].id
  member   = "serviceAccount:${google_service_account.backend.email}"
}

resource "google_project_iam_custom_role" "remediation" {
  for_each    = toset(var.remediation_project_ids)
  project     = each.value
  role_id     = "cloudginiRemediation"
  title       = "CloudGini remediation"
  description = "Only what CloudGini's allow-listed actions need."
  permissions = [
    "compute.instances.stop", "compute.instances.start", "compute.instances.setMachineType",
    "compute.addresses.delete", "compute.globalAddresses.delete",
    "compute.firewalls.update", "compute.networks.updatePolicy", "storage.buckets.setIamPolicy",
    "compute.zoneOperations.get", "compute.regionOperations.get", "compute.globalOperations.get",
  ]
}

resource "google_project_iam_member" "remediation" {
  for_each = toset(var.remediation_project_ids)
  project  = each.value
  role     = google_project_iam_custom_role.remediation[each.value].id
  member   = "serviceAccount:${google_service_account.backend.email}"
}

resource "google_project_iam_member" "billing_reader" {
  count   = var.billing_table == "" ? 0 : 1
  project = var.billing_dataset_project
  role    = "roles/bigquery.dataViewer"
  member  = "serviceAccount:${google_service_account.backend.email}"
}

resource "google_project_iam_member" "billing_jobs" {
  count   = var.billing_table == "" ? 0 : 1
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.backend.email}"
}

resource "google_project_iam_member" "sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.backend.email}"
}

# ---------------------------------------------------------------- secrets (values added with gcloud, never in Terraform)
resource "google_secret_manager_secret" "s" {
  for_each  = toset(["cloudgini-database-url", "cloudgini-api-keys", "cloudgini-anthropic-api-key"])
  secret_id = each.value
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_iam_member" "backend" {
  for_each  = google_secret_manager_secret.s
  secret_id = each.value.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.backend.email}"
}

# ---------------------------------------------------------------- database
resource "google_sql_database_instance" "db" {
  name                = "cloudgini"
  database_version    = "POSTGRES_16"
  deletion_protection = true
  settings {
    edition           = "ENTERPRISE"
    tier              = "db-f1-micro"
    availability_type = "ZONAL"
    ip_configuration {
      ipv4_enabled = true # reached only through the Cloud SQL connector; no authorised networks
      ssl_mode     = "ENCRYPTED_ONLY"
    }
    backup_configuration { enabled = true }
  }
  depends_on = [google_project_service.apis]
}

resource "google_sql_database" "app" {
  name     = "cloudgini"
  instance = google_sql_database_instance.db.name
}

# ---------------------------------------------------------------- services
resource "google_cloud_run_v2_service" "backend" {
  name     = "cloudgini-backend"
  location = var.region
  template {
    service_account = google_service_account.backend.email
    scaling { max_instance_count = 1 } # in-memory rate limiter: one instance
    volumes {
      name = "cloudsql"
      cloud_sql_instance { instances = [google_sql_database_instance.db.connection_name] }
    }
    containers {
      image = var.backend_image
      ports { container_port = 8000 }
      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }
      env {
        name  = "CLOUDGINI_GCP_PROJECTS"
        value = join(",", var.target_project_ids)
      }
      env {
        name  = "CLOUDGINI_GCP_BILLING_TABLE"
        value = var.billing_table
      }
      env {
        name  = "CLOUDGINI_SEED_SIMULATED"
        value = "true"
      }
      dynamic "env" {
        for_each = { CLOUDGINI_DATABASE_URL = "cloudgini-database-url", CLOUDGINI_API_KEYS = "cloudgini-api-keys", ANTHROPIC_API_KEY = "cloudgini-anthropic-api-key" }
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.s[env.value].secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }
  depends_on = [google_secret_manager_secret_iam_member.backend]
}

resource "google_cloud_run_v2_service" "frontend" {
  name     = "cloudgini-frontend"
  location = var.region
  template {
    service_account = google_service_account.frontend.email
    containers {
      image = var.frontend_image
      ports { container_port = 3000 }
      env {
        name  = "BACKEND_URL"
        value = google_cloud_run_v2_service.backend.uri
      }
    }
  }
}

# Both services are reachable from the internet; the backend requires an API key on every /api call.
resource "google_cloud_run_v2_service_iam_member" "public" {
  for_each = { backend = google_cloud_run_v2_service.backend.name, frontend = google_cloud_run_v2_service.frontend.name }
  name     = each.value
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}
