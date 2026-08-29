variable "project_id" {
  type        = string
  description = "Existing or SDK-created GCP project ID."
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "project_id must be a valid Google Cloud project ID."
  }
}

variable "receiver_cloud_run_region" {
  type        = string
  description = "Cloud Run receiver and job region."
  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]+[0-9]$", var.receiver_cloud_run_region))
    error_message = "receiver_cloud_run_region must be a provider region name."
  }
}

variable "control_database_id" {
  type    = string
  default = "control"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,62}$", var.control_database_id)) && var.control_database_id != "(default)"
    error_message = "control_database_id must be a non-default Firestore database ID."
  }
}

variable "runtime_database_id" {
  type    = string
  default = "runtime"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,62}$", var.runtime_database_id)) && var.runtime_database_id != "(default)"
    error_message = "runtime_database_id must be a non-default Firestore database ID."
  }
}

variable "control_database_location" {
  type = string
  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]+[0-9]$", var.control_database_location))
    error_message = "control_database_location must be a provider location name."
  }
}

variable "runtime_database_location" {
  type = string
  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]+[0-9]$", var.runtime_database_location))
    error_message = "runtime_database_location must be a provider location name."
  }
}

variable "eventarc_trigger_location" {
  type = string
  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]+[0-9]$", var.eventarc_trigger_location))
    error_message = "eventarc_trigger_location must be a provider location name."
  }
}

variable "eventarc_trigger_name" {
  type    = string
  default = "task-request-created"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,62}$", var.eventarc_trigger_name))
    error_message = "eventarc_trigger_name must contain only lowercase letters, digits, and hyphens."
  }
}

variable "request_document_path_pattern" {
  type        = string
  default     = "projects/{projectId}/workspaces/{workspaceId}/members/{firebaseUid}/requests/{requestId}"
  description = "Firestore document path pattern, without a leading slash."
  validation {
    condition     = !startswith(var.request_document_path_pattern, "/") && !strcontains(var.request_document_path_pattern, "//") && length(var.request_document_path_pattern) <= 512
    error_message = "The Firestore document path pattern must be a bounded relative path without empty segments."
  }
}

variable "authorized_ui_domains" {
  type        = list(string)
  default     = ["localhost"]
  description = "Explicit Firebase authorized domains; localhost is required for the approved local UI."
}

variable "identity_platform_google_web_client_id" {
  type      = string
  sensitive = true
}

variable "identity_platform_google_web_client_secret" {
  type        = string
  sensitive   = true
  description = "Web IdP secret. Terraform state and plans still contain this value; use an encrypted backend."
}

variable "firebase_web_app_display_name" {
  type    = string
  default = "ADK Harness Approval UI"
}

variable "eventarc_trigger_service_account_email" {
  type = string
}

variable "eventarc_receiver_service_account_id" {
  type    = string
  default = "eventarc-receiver"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.eventarc_receiver_service_account_id))
    error_message = "eventarc_receiver_service_account_id must be a valid service account ID."
  }
}

variable "worker_runtime_service_account_id" {
  type    = string
  default = "workspace-worker"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.worker_runtime_service_account_id))
    error_message = "worker_runtime_service_account_id must be a valid service account ID."
  }
}

variable "receiver_cloud_run_service_name" {
  type    = string
  default = "workspace-event-receiver"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,62}$", var.receiver_cloud_run_service_name))
    error_message = "receiver_cloud_run_service_name must contain only lowercase letters, digits, and hyphens."
  }
}

variable "worker_cloud_run_job_name" {
  type    = string
  default = "workspace-worker"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,62}$", var.worker_cloud_run_job_name))
    error_message = "worker_cloud_run_job_name must contain only lowercase letters, digits, and hyphens."
  }
}

variable "receiver_container_image" {
  type = string
}

variable "worker_container_image" {
  type = string
}

variable "workspace_secret_id" {
  type        = string
  default     = "workspace-grants"
  description = "Secret Manager container for explicitly consented Workspace grants. No secret value is managed here."
}

variable "workspace_secret_version" {
  type        = string
  default     = "1"
  description = "Exact numeric Secret Manager version approved for this deployment."
  validation {
    condition     = can(regex("^[1-9][0-9]*$", var.workspace_secret_version))
    error_message = "workspace_secret_version must be an exact positive numeric version."
  }
}

variable "policy_version" {
  type        = string
  default     = "policy-1"
  description = "Immutable policy version checked by the worker before mutations."
  validation {
    condition     = length(var.policy_version) > 0 && length(var.policy_version) <= 200
    error_message = "policy_version must be a bounded nonempty value."
  }
}

variable "vertex_location" {
  type        = string
  default     = "global"
  description = "Vertex AI location used by the ADK planner."
}

variable "adk_model" {
  type        = string
  default     = "gemini-3.5-flash"
  description = "Approved Gemini model identifier for planning."
  validation {
    condition     = can(regex("^gemini-[a-z0-9.-]+$", var.adk_model))
    error_message = "adk_model must be a Gemini model identifier."
  }
}
