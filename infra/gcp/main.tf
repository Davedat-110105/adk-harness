terraform {
  required_version = "= 1.16.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "8.0.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "8.0.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.receiver_cloud_run_region
}

provider "google-beta" {
  project = var.project_id
  region  = var.receiver_cloud_run_region
}

# Firebase project and Web app resources remain on the preview beta provider.
resource "google_firebase_project" "workspace" {
  provider = google-beta
  project  = var.project_id
}

resource "google_firebase_web_app" "approval" {
  provider     = google-beta
  project      = var.project_id
  display_name = var.firebase_web_app_display_name
  depends_on   = [google_firebase_project.workspace]
}

resource "google_identity_platform_config" "auth" {
  project            = var.project_id
  authorized_domains = var.authorized_ui_domains
  depends_on         = [google_firebase_project.workspace]
}

resource "google_identity_platform_default_supported_idp_config" "google" {
  project       = var.project_id
  idp_id        = "google.com"
  enabled       = true
  client_id     = var.identity_platform_google_web_client_id
  client_secret = var.identity_platform_google_web_client_secret
  depends_on    = [google_identity_platform_config.auth]
}

data "google_firebase_web_app_config" "approval" {
  provider   = google-beta
  project    = var.project_id
  web_app_id = google_firebase_web_app.approval.app_id
}

resource "google_firestore_database" "control" {
  project         = var.project_id
  name            = var.control_database_id
  location_id     = var.control_database_location
  type            = "FIRESTORE_NATIVE"
  deletion_policy = "ABANDON"
}

resource "google_firestore_database" "runtime" {
  project         = var.project_id
  name            = var.runtime_database_id
  location_id     = var.runtime_database_location
  type            = "FIRESTORE_NATIVE"
  deletion_policy = "ABANDON"
  lifecycle {
    precondition {
      condition     = var.control_database_id != var.runtime_database_id
      error_message = "Control and runtime Firestore database IDs must be distinct."
    }
  }
}

resource "google_service_account" "eventarc_receiver" {
  project      = var.project_id
  account_id   = var.eventarc_receiver_service_account_id
  display_name = "Eventarc authenticated receiver"
}

resource "google_service_account" "worker" {
  project      = var.project_id
  account_id   = var.worker_runtime_service_account_id
  display_name = "Workspace worker runtime"
}

resource "google_cloud_run_v2_service" "receiver" {
  project  = var.project_id
  name     = var.receiver_cloud_run_service_name
  location = var.receiver_cloud_run_region
  template {
    service_account = google_service_account.eventarc_receiver.email
    containers {
      image   = var.receiver_container_image
      command = ["functions-framework"]
      # functions-framework resolves --source as a file path, not a module name.
      args = [
        "--target=receiver_entrypoint",
        "--source=/usr/local/lib/python3.12/site-packages/adk_harness/cloud/entrypoints.py",
        "--signature-type=cloudevent",
      ]
      env {
        name  = "ADK_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "ADK_FIREBASE_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "ADK_CONTROL_DATABASE"
        value = var.control_database_id
      }
      env {
        name  = "ADK_RUNTIME_DATABASE"
        value = var.runtime_database_id
      }
      env {
        name  = "ADK_WORKER_JOB_NAME"
        value = google_cloud_run_v2_job.worker.name
      }
      env {
        name  = "ADK_EVENTARC_AUTH_ID"
        value = var.eventarc_trigger_service_account_email
      }
    }
  }
}

resource "google_cloud_run_v2_job" "worker" {
  project  = var.project_id
  name     = var.worker_cloud_run_job_name
  location = var.receiver_cloud_run_region
  template {
    template {
      service_account = google_service_account.worker.email
      containers {
        image   = var.worker_container_image
        command = ["python"]
        args    = ["-m", "adk_harness.cloud.entrypoints"]
        env {
          name  = "ADK_PROJECT_ID"
          value = var.project_id
        }
        env {
          name  = "ADK_CONTROL_DATABASE"
          value = var.control_database_id
        }
        env {
          name  = "ADK_CLIENT_ID"
          value = var.identity_platform_google_web_client_id
        }
        env {
          name  = "ADK_MODEL_RUNTIME_PROJECT_ID"
          value = var.project_id
        }
        env {
          name  = "ADK_MODEL_RUNTIME_LOCATION"
          value = var.vertex_location
        }
        env {
          name  = "ADK_MODEL_RUNTIME_MODEL"
          value = var.adk_model
        }
        env {
          name  = "ADK_RUNTIME_DATABASE"
          value = var.runtime_database_id
        }
        env {
          name = "ADK_WORKER_JOB_NAME"
          # Keep the job's fully qualified name stable without introducing a
          # self-reference cycle while Terraform is constructing the job.
          value = "projects/${var.project_id}/locations/${var.receiver_cloud_run_region}/jobs/${var.worker_cloud_run_job_name}"
        }
        env {
          name  = "ADK_POLICY_VERSION"
          value = var.policy_version
        }
        env {
          name  = "ADK_VERTEX_LOCATION"
          value = var.vertex_location
        }
        env {
          name  = "ADK_MODEL"
          value = var.adk_model
        }
        env {
          name  = "ADK_WORKSPACE_GRANT_SECRET_VERSION"
          value = "projects/${var.project_id}/secrets/${var.workspace_secret_id}/versions/${var.workspace_secret_version}"
        }
        env {
          name  = "ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS"
          value = "false"
        }
        env {
          name  = "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"
          value = "NO_CONTENT"
        }
      }
    }
  }
}

resource "google_cloud_run_v2_service_iam_member" "receiver_invoker" {
  project  = var.project_id
  location = var.receiver_cloud_run_region
  name     = google_cloud_run_v2_service.receiver.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${var.eventarc_trigger_service_account_email}"
}

resource "google_cloud_run_v2_job_iam_member" "worker_executor" {
  project  = var.project_id
  location = var.receiver_cloud_run_region
  name     = google_cloud_run_v2_job.worker.name
  role     = "roles/run.jobsExecutorWithOverrides"
  member   = google_service_account.eventarc_receiver.member
}

resource "google_project_iam_member" "eventarc_receiver" {
  project = var.project_id
  role    = "roles/eventarc.eventReceiver"
  member  = "serviceAccount:${var.eventarc_trigger_service_account_email}"
}

resource "google_project_iam_member" "worker_control_viewer" {
  project = var.project_id
  role    = "roles/datastore.viewer"
  member  = "serviceAccount:${google_service_account.worker.email}"
  condition {
    title       = "worker-control-database-read"
    description = "Worker read access to the control database only"
    expression  = "resource.type == \"firestore.googleapis.com/Database\" && resource.name == \"projects/${var.project_id}/databases/${var.control_database_id}\""
  }
}

resource "google_project_iam_member" "worker_runtime_user" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.worker.email}"
  condition {
    title       = "worker-runtime-database-write"
    description = "Worker read/write access to the runtime database only"
    expression  = "resource.type == \"firestore.googleapis.com/Database\" && resource.name == \"projects/${var.project_id}/databases/${var.runtime_database_id}\""
  }
}

resource "google_project_iam_member" "receiver_control_viewer" {
  project = var.project_id
  role    = "roles/datastore.viewer"
  member  = "serviceAccount:${google_service_account.eventarc_receiver.email}"
  condition {
    title       = "receiver-control-database-read"
    description = "Receiver can read and claim control requests only"
    expression  = "resource.type == \"firestore.googleapis.com/Database\" && resource.name == \"projects/${var.project_id}/databases/${var.control_database_id}\""
  }
}

resource "google_project_iam_member" "receiver_runtime_writer" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.eventarc_receiver.email}"
  condition {
    title       = "receiver-runtime-database-write"
    description = "Receiver can write runtime checkpoints only"
    expression  = "resource.type == \"firestore.googleapis.com/Database\" && resource.name == \"projects/${var.project_id}/databases/${var.runtime_database_id}\""
  }
}

resource "google_project_iam_member" "worker_trace_writer" {
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.worker.email}"
}

resource "google_project_iam_member" "worker_vertex_model_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.worker.email}"
}

resource "google_project_iam_member" "receiver_trace_writer" {
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.eventarc_receiver.email}"
}

resource "google_secret_manager_secret" "workspace_grants" {
  project   = var.project_id
  secret_id = var.workspace_secret_id
  replication {
    auto {}
  }
  deletion_policy = "ABANDON"
}

resource "google_secret_manager_secret_iam_member" "worker_workspace_grants_reader" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.workspace_grants.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.worker.email}"
}

resource "google_eventarc_trigger" "task_request_created" {
  project                 = var.project_id
  name                    = var.eventarc_trigger_name
  location                = var.eventarc_trigger_location
  service_account         = var.eventarc_trigger_service_account_email
  event_data_content_type = "application/protobuf"

  matching_criteria {
    attribute = "type"
    value     = "google.cloud.firestore.document.v1.created.withAuthContext"
  }
  matching_criteria {
    attribute = "database"
    value     = var.control_database_id
  }
  matching_criteria {
    attribute = "document"
    operator  = "match-path-pattern"
    value     = var.request_document_path_pattern
  }
  destination {
    cloud_run_service {
      service = google_cloud_run_v2_service.receiver.name
      region  = var.receiver_cloud_run_region
      path    = "/eventarc/firestore"
    }
  }
  depends_on = [
    google_firestore_database.control,
    google_cloud_run_v2_service_iam_member.receiver_invoker,
    google_project_iam_member.eventarc_receiver,
  ]
  lifecycle {
    precondition {
      condition     = var.eventarc_trigger_location == var.control_database_location
      error_message = "A Firestore trigger location must equal the watched database location."
    }
  }
}

# Terraform intentionally does not manage Firebase Rules releases. The
# official firebaserules.v1 client publishes named releases with attachmentPoint
# and checkpoints them, because provider 8.0.0 has no attachment_point field.
