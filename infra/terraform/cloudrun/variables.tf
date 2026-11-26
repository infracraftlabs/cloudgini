variable "project_id" {
  description = "Project that hosts CloudGini itself (Cloud Run, Cloud SQL)."
  type        = string
}

variable "region" {
  type    = string
  default = "europe-west1"
}

variable "target_project_ids" {
  description = "Projects CloudGini may scan (read-only roles are granted on each)."
  type        = list(string)
  default     = []
}

variable "remediation_project_ids" {
  description = "Subset of target projects where the narrow remediation role is granted. Empty = read-only everywhere."
  type        = list(string)
  default     = []
}

variable "backend_image" {
  description = "Backend image, e.g. europe-west1-docker.pkg.dev/PROJECT/cloudgini/backend:TAG"
  type        = string
}

variable "frontend_image" {
  type = string
}

variable "billing_table" {
  description = "BigQuery billing export table (project.dataset.table). Empty = no cost data."
  type        = string
  default     = ""
}

variable "billing_dataset_project" {
  description = "Project holding the billing export dataset (for the BigQuery read grant)."
  type        = string
  default     = ""
}
