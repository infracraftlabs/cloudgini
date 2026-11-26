variable "project_id" {
  description = "A DEDICATED, empty GCP project for the CloudGini demo. Never a project with real workloads."
  type        = string
}

variable "region" {
  type    = string
  default = "europe-west1"
}

variable "zone" {
  type    = string
  default = "europe-west1-b"
}

variable "confirm_dedicated_demo_project" {
  description = "Set to true to confirm project_id is a throwaway project used only for this demo."
  type        = bool
  default     = false
  validation {
    condition     = var.confirm_dedicated_demo_project
    error_message = "Set confirm_dedicated_demo_project = true only for a dedicated, isolated demo project."
  }
}

variable "install_ops_agent" {
  description = "Install the Ops Agent on the demo VMs so memory metrics exist (without it, VM rightsizing stays in manual review)."
  type        = bool
  default     = true
}

