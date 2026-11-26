terraform {
  required_version = ">= 1.6"
  required_providers {
    google = { source = "hashicorp/google", version = "~> 6.0" }
  }
  # Use a remote backend (e.g. a GCS bucket with versioning) for real deployments.
}

provider "google" {
  project = var.project_id
  region  = var.region
}
