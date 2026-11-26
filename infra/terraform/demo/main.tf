# CloudGini demo estate: a handful of deliberately wasteful or insecure resources.
# Everything is labelled env=dev so CloudGini's allow-listed actions may touch it.
# See docs/demo-walkthrough.md for expected findings, cost and cleanup.

locals {
  labels           = { env = "dev", owner = "cloudgini-demo", purpose = "cloudgini-demo" }
  ops_agent_script = <<-EOT
    #!/bin/bash
    curl -sSO https://dl.google.com/cloudagents/add-google-cloud-ops-agent-repo.sh
    bash add-google-cloud-ops-agent-repo.sh --also-install
  EOT
  ops_agent        = var.install_ops_agent ? local.ops_agent_script : ""
}

resource "google_project_service" "apis" {
  for_each = toset([
    "compute.googleapis.com", "storage.googleapis.com", "monitoring.googleapis.com",
    "cloudasset.googleapis.com", "iam.googleapis.com", "logging.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

resource "google_compute_network" "demo" {
  name                    = "cloudgini-demo"
  auto_create_subnetworks = false
  depends_on              = [google_project_service.apis]
}

resource "google_compute_subnetwork" "demo" {
  name          = "cloudgini-demo"
  network       = google_compute_network.demo.id
  ip_cidr_range = "10.10.0.0/24"
}

# 1. Oversized VM: 4 vCPU running an idle OS -> rightsize to e2-standard-2.
resource "google_compute_instance" "oversized" {
  name         = "cg-demo-oversized"
  machine_type = "e2-standard-4"
  labels       = local.labels
  tags         = ["cg-demo-ssh"]
  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 10
      type  = "pd-standard"
    }
  }
  # 3. Big disk: attached SSD that sees almost no I/O -> pd-balanced.
  attached_disk {
    source      = google_compute_disk.big.id
    device_name = "cg-demo-big-ssd"
  }
  network_interface {
    subnetwork = google_compute_subnetwork.demo.id # no external IP
  }
  metadata_startup_script = local.ops_agent
  shielded_instance_config { enable_secure_boot = true }
}

# 2. Underused VM: does nothing -> stop (CloudGini can do this after approval).
resource "google_compute_instance" "underused" {
  name         = "cg-demo-underused"
  machine_type = "e2-standard-2"
  labels       = local.labels
  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 10
      type  = "pd-standard"
    }
  }
  network_interface { subnetwork = google_compute_subnetwork.demo.id }
  metadata_startup_script = local.ops_agent
  shielded_instance_config { enable_secure_boot = true }
}

resource "google_compute_disk" "big" {
  name   = "cg-demo-big-ssd"
  type   = "pd-ssd"
  size   = 100
  labels = local.labels
}

# 4. Unattached disk (shows up as a cleanup candidate after 30 days unattached).
resource "google_compute_disk" "unattached" {
  name   = "cg-demo-unattached"
  type   = "pd-standard"
  size   = 50
  labels = local.labels
}

# 5. Unused static IP -> release (irreversible, needs typed confirmation).
resource "google_compute_address" "unused" {
  name   = "cg-demo-unused-ip"
  labels = local.labels
}

# 6. Snapshot of the unattached disk. It becomes an "orphaned snapshot" only when its source disk
#    is gone AND it is older than the retention threshold (90 days by default).
resource "google_compute_snapshot" "old" {
  name        = "cg-demo-old-snapshot"
  source_disk = google_compute_disk.unattached.id
  labels      = local.labels
}

# 7. Public test bucket (one harmless object) -> remove public access.
resource "google_storage_bucket" "public" {
  name                        = "${var.project_id}-cg-demo-public"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "inherited"
  force_destroy               = true
  labels                      = local.labels
}

resource "google_storage_bucket_object" "hello" {
  name    = "hello.txt"
  bucket  = google_storage_bucket.public.name
  content = "CloudGini demo object. Nothing sensitive."
}

resource "google_storage_bucket_iam_member" "public_read" {
  bucket = google_storage_bucket.public.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

# 8. Permissive test IAM: a service account with Editor on the project (no keys are created).
resource "google_service_account" "overprivileged" {
  account_id   = "cg-demo-overprivileged"
  display_name = "CloudGini demo: over-privileged (test only)"
  description  = "env=dev owner=cloudgini-demo"
}

resource "google_project_iam_member" "overprivileged_editor" {
  project = var.project_id
  role    = "roles/editor"
  member  = "serviceAccount:${google_service_account.overprivileged.email}"
}

# 9. SSH open to the internet -> restrict to the IAP range.
resource "google_compute_firewall" "open_ssh" {
  name          = "cg-demo-open-ssh"
  network       = google_compute_network.demo.name
  direction     = "INGRESS"
  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["cg-demo-ssh"]
  description   = "env=dev owner=cloudgini-demo"
  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}
