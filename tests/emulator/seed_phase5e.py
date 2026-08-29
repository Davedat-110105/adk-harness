"""Seed only trusted fixture documents through google-cloud-firestore.

This script is deliberately emulator-only. It never falls back to ADC or a
live project and is invoked by the retained Rules test before client reads.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore


def timestamp(value: dict[str, Any]) -> datetime:
    if (
        set(value) != {"type", "seconds", "nanoseconds"}
        or value["type"] != "firestore/timestamp/1.0"
    ):
        raise ValueError("invalid timestamp mirror")
    return datetime.fromtimestamp(value["seconds"], tz=UTC).replace(
        microsecond=value["nanoseconds"] // 1000
    )


def materialize_approval(value: dict[str, Any]) -> dict[str, Any]:
    result = dict(value)
    for key in ("expires_at_ts", "approved_at_ts"):
        if isinstance(result.get(key), dict):
            result[key] = timestamp(result[key])
    return result


def materialize_envelope(value: Any) -> Any:
    """Convert only documented native mirror slots.

    Canonical model maps can legally contain nested ``*_ts`` strings; a
    recursive timestamp conversion would silently change their approved
    payload before the Lite client sees it.
    """
    if not isinstance(value, dict):
        return value
    result: dict[str, Any] = {}
    for key, item in value.items():
        if key in {"expires_at_ts", "approved_at_ts"} and isinstance(item, dict):
            result[key] = timestamp(item)
        elif key == "approval" and isinstance(item, dict):
            result[key] = materialize_approval(item)
        else:
            result[key] = item
    return result


def write(client: firestore.Client, path: str, value: dict[str, Any]) -> None:
    client.document(path).set(materialize_envelope(value))


def seed_runtime_cases(runtime, *, project, config, uid, manifest, envelope) -> None:
    """Add valid-boundary and malformed owner-authored runtime documents."""
    task = manifest["task_id"]
    runtime_prefix = (
        f"projects/{project}/workspaces/{config['workspace_id']}/users/{uid}/tasks/{task}"
    )
    write(runtime, f"{runtime_prefix}/manifests/latest", manifest)
    write(runtime, f"{runtime_prefix}/results/{envelope['result_id']}", envelope)
    expired = dict(manifest)
    expired["task_id"] = "task-expired"
    expired["expires_at_ts"] = {
        "type": "firestore/timestamp/1.0",
        "seconds": 1,
        "nanoseconds": 0,
    }
    expired_prefix = (
        f"projects/{project}/workspaces/{config['workspace_id']}/users/{uid}/tasks/task-expired"
    )
    write(runtime, f"{expired_prefix}/manifests/latest", expired)
    malformed_scope = dict(manifest)
    malformed_scope["task_id"] = "task-malformed-scope"
    malformed_scope["scope"] = [{"not": "a string"}]
    malformed_scope_prefix = (
        f"projects/{project}/workspaces/{config['workspace_id']}"
        f"/users/{uid}/tasks/task-malformed-scope"
    )
    write(runtime, f"{malformed_scope_prefix}/manifests/latest", malformed_scope)
    oversized_scope = dict(manifest)
    oversized_scope["task_id"] = "task-oversized-scope"
    oversized_scope["scope"] = [f"scope-{index}" for index in range(21)]
    oversized_scope_prefix = (
        f"projects/{project}/workspaces/{config['workspace_id']}"
        f"/users/{uid}/tasks/task-oversized-scope"
    )
    write(runtime, f"{oversized_scope_prefix}/manifests/latest", oversized_scope)
    scope_20 = dict(manifest)
    scope_20["task_id"] = "task-scope-20"
    scope_20["scope"] = [f"scope-{index}" for index in range(20)]
    scope_20_prefix = (
        f"projects/{project}/workspaces/{config['workspace_id']}/users/{uid}/tasks/task-scope-20"
    )
    write(runtime, f"{scope_20_prefix}/manifests/latest", scope_20)
    malformed = dict(envelope)
    malformed["result_id"] = "f" * 64
    malformed["result_hash"] = "f" * 64
    write(runtime, f"{runtime_prefix}/results/{'f' * 64}", malformed)
    malformed_payload = dict(envelope)
    malformed_payload["payload"] = dict(envelope["payload"])
    malformed_payload["payload"]["unexpected"] = "owner-authored extra"
    malformed_payload_prefix = (
        f"projects/{project}/workspaces/{config['workspace_id']}"
        f"/users/{uid}/tasks/task-malformed-payload"
    )
    write(runtime, f"{malformed_payload_prefix}/results/{envelope['result_id']}", malformed_payload)
    malformed_kind = dict(envelope)
    malformed_kind["payload"] = dict(envelope["payload"])
    malformed_kind["payload"]["kind"] = "changeset_result"
    malformed_kind_prefix = (
        f"projects/{project}/workspaces/{config['workspace_id']}"
        f"/users/{uid}/tasks/task-malformed-kind"
    )
    write(runtime, f"{malformed_kind_prefix}/results/{envelope['result_id']}", malformed_kind)


def seed_membership_cases(control, project, config, member) -> None:
    """Add namespace and expiry failures under otherwise valid member paths."""
    expired_member = dict(member)
    expired_member["firebase_uid"] = "firebase-expired"
    expired_member["google_sub"] = "google-expired"
    expired_member["expires_at"] = datetime.fromtimestamp(1, tz=UTC)
    control.document(
        f"projects/{project}/workspaces/{config['workspace_id']}/members/firebase-expired"
    ).set(expired_member)
    wrong_namespace_member = dict(member)
    wrong_namespace_member["firebase_uid"] = "firebase-namespace"
    wrong_namespace_member["google_sub"] = "google-namespace"
    wrong_namespace_member["project_id"] = "demo-other-project"
    control.document(
        f"projects/{project}/workspaces/{config['workspace_id']}/members/firebase-namespace"
    ).set(wrong_namespace_member)


def main() -> int:
    emulator = os.environ.get("FIRESTORE_EMULATOR_HOST", "")
    project = os.environ.get("FIRESTORE_PROJECT", "demo-adk-wire")
    if not (emulator.startswith("127.0.0.1:") or emulator.startswith("localhost:")):
        raise SystemExit("FIRESTORE_EMULATOR_HOST must be loopback")
    if not project.startswith("demo-"):
        raise SystemExit("seed project must be a demo project")
    if len(sys.argv) != 2:
        raise SystemExit("usage: seed_phase5e.py FIXTURES.json")
    fixtures = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    config = fixtures["config"]
    if config["project_id"] != project:
        raise SystemExit("fixture project does not match guarded demo project")
    uid, subject = "firebase-1", "google-1"
    member_path = f"projects/{project}/workspaces/{config['workspace_id']}/members/{uid}"
    control = firestore.Client(
        project=project, database=config["control_database_id"], credentials=AnonymousCredentials()
    )
    runtime = firestore.Client(
        project=project, database=config["runtime_database_id"], credentials=AnonymousCredentials()
    )
    member = {
        "schema_version": 1,
        "project_id": project,
        "workspace_id": config["workspace_id"],
        "firebase_uid": uid,
        "google_sub": subject,
        "status": "active",
        "expires_at": datetime.fromtimestamp(4102444800, tz=UTC),
    }
    try:
        control.document(member_path).set(member)
        runtime.document(member_path).set(member)
        manifest = fixtures["manifest"]
        envelope = fixtures["result_envelope"]
        seed_runtime_cases(
            runtime,
            project=project,
            config=config,
            uid=uid,
            manifest=manifest,
            envelope=envelope,
        )
        seed_membership_cases(control, project, config, member)
    finally:
        control.close()
        runtime.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
