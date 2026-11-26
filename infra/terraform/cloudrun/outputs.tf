output "frontend_url" { value = google_cloud_run_v2_service.frontend.uri }
output "backend_url" { value = google_cloud_run_v2_service.backend.uri }
output "backend_service_account" { value = google_service_account.backend.email }
output "sql_connection_name" { value = google_sql_database_instance.db.connection_name }
