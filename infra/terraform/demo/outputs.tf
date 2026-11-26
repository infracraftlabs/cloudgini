output "public_test_url" { value = "https://storage.googleapis.com/${google_storage_bucket.public.name}/hello.txt" }
output "next_steps" {
  value = "Set CLOUDGINI_GCP_PROJECTS=${var.project_id}, restart the backend and scan. See docs/demo-walkthrough.md."
}
