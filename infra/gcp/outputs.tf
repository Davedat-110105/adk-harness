output "project_id" {
  value = var.project_id
}

output "control_database_name" {
  value = google_firestore_database.control.name
}

output "runtime_database_name" {
  value = google_firestore_database.runtime.name
}

output "firebase_web_app_id" {
  value = google_firebase_web_app.approval.app_id
}

output "firebase_web_config" {
  value = {
    api_key             = data.google_firebase_web_app_config.approval.api_key
    auth_domain         = data.google_firebase_web_app_config.approval.auth_domain
    app_id              = data.google_firebase_web_app_config.approval.web_app_id
    messaging_sender_id = data.google_firebase_web_app_config.approval.messaging_sender_id
    project_id          = data.google_firebase_web_app_config.approval.project
    storage_bucket      = data.google_firebase_web_app_config.approval.storage_bucket
  }
  sensitive = true
}

output "receiver_service_name" {
  value = google_cloud_run_v2_service.receiver.name
}

output "worker_job_name" {
  value = google_cloud_run_v2_job.worker.name
}

output "receiver_runtime_service_account_email" {
  value = google_service_account.eventarc_receiver.email
}

output "worker_runtime_service_account_email" {
  value = google_service_account.worker.email
}

output "rules_publication" {
  value = "Publish both named Firestore Rules releases via the official firebaserules.v1 SDK after Terraform."
}

output "terraform_handoff" {
  description = "Nonsecret values consumed by the SDK Rules publication and runtime verification stages."
  value = {
    project_id                             = var.project_id
    receiver_cloud_run_region              = var.receiver_cloud_run_region
    control_database_id                    = google_firestore_database.control.name
    runtime_database_id                    = google_firestore_database.runtime.name
    control_database_location              = var.control_database_location
    runtime_database_location              = var.runtime_database_location
    eventarc_trigger_location              = var.eventarc_trigger_location
    eventarc_trigger_name                  = var.eventarc_trigger_name
    request_document_path_pattern          = var.request_document_path_pattern
    authorized_ui_domains                  = var.authorized_ui_domains
    identity_platform_google_web_client_id = nonsensitive(var.identity_platform_google_web_client_id)
    firebase_web_app_display_name          = var.firebase_web_app_display_name
    eventarc_trigger_service_account_email = var.eventarc_trigger_service_account_email
    eventarc_receiver_service_account_id   = var.eventarc_receiver_service_account_id
    worker_runtime_service_account_id      = var.worker_runtime_service_account_id
    receiver_cloud_run_service_name        = google_cloud_run_v2_service.receiver.name
    worker_cloud_run_job_name              = google_cloud_run_v2_job.worker.name
    receiver_container_image               = var.receiver_container_image
    worker_container_image                 = var.worker_container_image
    workspace_secret_id                    = var.workspace_secret_id
    workspace_secret_version               = var.workspace_secret_version
    receiver_runtime_service_account_email = google_service_account.eventarc_receiver.email
    worker_runtime_service_account_email   = google_service_account.worker.email
    policy_version                         = var.policy_version
    vertex_location                        = var.vertex_location
    adk_model                              = var.adk_model
    firebase_web_app_id                    = google_firebase_web_app.approval.app_id
    rules_source_version                   = "rules-v1"
  }
}
