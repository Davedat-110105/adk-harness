"""Supported local setup and Antigravity diagnostics."""

from __future__ import annotations

import argparse
import asyncio
import importlib.resources
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from adk_harness.auth.credentials import (
    CloudGrantChallenge,
    CredentialPurpose,
    SecureCredentialStore,
)
from adk_harness.auth.google import (
    AuthStatus,
    GoogleAuthenticator,
    GoogleAuthError,
    LocalApprovalBridge,
    LocalApprovalSession,
    verify_firebase_identity,
)
from adk_harness.integrations.antigravity import AntigravityIntegration

__all__ = ["main"]


async def _doctor() -> int:
    result = await AntigravityIntegration().discover()
    print("antigravity")
    print("  available:", result.get("available", False))
    if result.get("detail"):
        print("  detail:", result["detail"])
    return 0 if result.get("available") else 1


_DEFAULT_SCOPES = {
    CredentialPurpose.PROVISIONING: ("openid", "https://www.googleapis.com/auth/cloud-platform"),
    CredentialPurpose.WORKSPACE: ("openid", "https://www.googleapis.com/auth/calendar.events"),
}


def _client_config(path: str | None) -> dict[str, Any]:
    configured = path or os.environ.get("ADK_HARNESS_GOOGLE_CLIENT_CONFIG")
    if not configured:
        raise GoogleAuthError("Google OAuth client configuration is not configured")
    try:
        return json.loads(Path(configured).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise GoogleAuthError("Google OAuth client configuration could not be loaded") from None


def _build_auth(path: str | None = None) -> GoogleAuthenticator:
    return GoogleAuthenticator(
        client_config=_client_config(path),
        store=SecureCredentialStore(),
    )


def _auth_status(
    purpose: CredentialPurpose,
    *,
    client_config: str | None = None,
    subject: str | None = None,
) -> dict[str, object]:
    """Return only non-secret local authentication metadata."""
    try:
        status = _build_auth(client_config).status(purpose, subject=subject)
    except (GoogleAuthError, RuntimeError, ValueError):
        return {"stored": False, "authenticated": False, "reason": "authentication unavailable"}
    return {
        "stored": status.stored,
        "authenticated": status.authenticated,
        "subject": status.subject,
        "purpose": status.purpose.value,
        "granted_scopes": status.granted_scopes,
        "reason": status.reason,
    }


def _print_status(value: AuthStatus | dict[str, object]) -> None:
    values = value if isinstance(value, dict) else {
        "stored": value.stored,
        "authenticated": value.authenticated,
        "subject": value.subject,
        "purpose": value.purpose.value,
        "granted_scopes": value.granted_scopes,
        "reason": value.reason,
    }
    for key, item in values.items():
        if item is not None:
            print(f"{key}: {item}")


def _status(client_config: str | None = None, subject: str | None = None) -> int:
    code = 0
    for purpose in CredentialPurpose:
        if client_config is None and subject is None:
            value = _auth_status(purpose)
        else:
            value = _auth_status(purpose, client_config=client_config, subject=subject)
        print(purpose.value)
        _print_status(value)
        if value.get("stored") and not value.get("authenticated"):
            code = 1
    return code


def _login(args: argparse.Namespace) -> int:
    purpose = CredentialPurpose(args.purpose)
    try:
        status = _build_auth(args.client_config).login(
            purpose,
            scopes=tuple(args.scope or _DEFAULT_SCOPES[purpose]),
        )
    except (GoogleAuthError, RuntimeError, ValueError):
        print("Google login failed or was cancelled", file=sys.stderr)
        return 1
    print(f"logged in: {status.subject}")
    return 0


def _logout(args: argparse.Namespace) -> int:
    try:
        auth = _build_auth(args.client_config)
        subjects = auth.store.subjects()
        if args.subject is None and len(subjects) > 1:
            raise GoogleAuthError("an explicit subject is required when multiple accounts exist")
        subject = args.subject or (subjects[0] if subjects else None)
        if not subject:
            print("no stored credentials")
            return 0
        status = auth.logout(subject=subject, purpose=CredentialPurpose(args.purpose))
    except (GoogleAuthError, RuntimeError, ValueError):
        print("Google logout failed", file=sys.stderr)
        return 1
    print(status.reason or "local credentials deleted")
    return 0


def _ui(args: argparse.Namespace) -> int:  # noqa: PLR0915
    """Start the trusted browser UI; capability is opened, never printed."""
    bridge: LocalApprovalBridge | None = None
    try:
        auth = _build_auth(args.client_config)
        subjects = auth.store.subjects()
        if args.subject is None and len(subjects) > 1:
            raise GoogleAuthError("an explicit subject is required when multiple accounts exist")
        subject = args.subject or (subjects[0] if subjects else None)
        if not subject or not auth.status(
            CredentialPurpose.PROVISIONING, subject=subject
        ).authenticated:
            raise GoogleAuthError("a verified Google login is required before opening the UI")
        firebase_config = (
            json.loads(Path(args.firebase_config).read_text(encoding="utf-8"))
            if args.firebase_config
            else {}
        )
        firebase_project_id = str(firebase_config.get("projectId", ""))
        cloud_destination = args.cloud_destination
        cloud_challenge = None
        if cloud_destination:
            workspace_status = auth.status(CredentialPurpose.WORKSPACE, subject=subject)
            if not workspace_status.authenticated:
                raise GoogleAuthError("a verified Workspace grant is required for cloud consent")
            workspace_record = auth.store.load(subject, CredentialPurpose.WORKSPACE)
            if workspace_record is None:
                raise GoogleAuthError("a verified Workspace grant is required for cloud consent")
            cloud_challenge = CloudGrantChallenge.issue(
                subject=subject,
                destination=cloud_destination,
                scopes=workspace_record.granted_scopes,
            )
        session = LocalApprovalSession.create()

        def firebase_binding(body: dict[str, object]) -> dict[str, object]:
            token = body.get("firebaseIdToken")
            if not firebase_project_id or not isinstance(token, str):
                raise GoogleAuthError("Firebase setup is not complete")
            identity = verify_firebase_identity(
                token,
                firebase_project_id=firebase_project_id,
                expected_google_subject=subject,
            )
            return {"firebaseUid": identity.firebase_uid, "googleSubject": identity.google_subject}

        def cloud_consent(body: dict[str, object]) -> dict[str, object]:
            token = body.get("firebaseIdToken")
            if cloud_challenge is None or not firebase_project_id or not isinstance(token, str):
                raise GoogleAuthError("cloud grant setup is not complete")
            verify_firebase_identity(
                token,
                firebase_project_id=firebase_project_id,
                expected_google_subject=subject,
            )
            from adk_harness.auth.credentials import WorkspaceGrantConsent

            consent = WorkspaceGrantConsent.create(
                subject=subject,
                destination=cloud_challenge.destination,
                scopes=cloud_challenge.scopes,
            )
            auth.upload_workspace_grant_to_secret_manager(
                subject=subject,
                destination=cloud_challenge.destination,
                scopes=cloud_challenge.scopes,
                consent=consent,
            )
            return {"status": "cloud grant stored"}

        def setup_confirmation(body: dict[str, object]) -> dict[str, object]:
            if body.get("googleSubject") != subject:
                raise GoogleAuthError("setup confirmation account mismatch")
            return {"status": "local setup confirmation received", "setupOnly": True}

        bootstrap: dict[str, object] = {
            "googleSubject": subject,
            "firebaseConfig": firebase_config or None,
            "setupOnly": not bool(firebase_project_id),
        }
        sync_engine = None
        sync_callbacks: dict[str, Any] = {}
        workflow_value: dict[str, Any] | None = None
        if args.workflow_config or args.outbox:
            if not args.workflow_config or not args.outbox:
                raise GoogleAuthError("workflow UI requires both --workflow-config and --outbox")
            from adk_harness.workflow.outbox import Outbox
            from adk_harness.workflow.sync import SyncEngine
            try:
                loaded = json.loads(Path(args.workflow_config).read_text(encoding="utf-8"))
                if not isinstance(loaded, dict):
                    raise ValueError("workflow configuration must be an object")
                workflow_value = loaded
                sync_engine = SyncEngine(Outbox(args.outbox), workflow_config=loaded)
                sync_callbacks = sync_engine.bridge_callbacks()
                bootstrap["workflow"] = {"enabled": True, "outbox": str(args.outbox)}
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                raise GoogleAuthError(f"workflow configuration could not be loaded: {exc}") from exc
        if cloud_challenge is not None:
            bootstrap["cloudGrant"] = {
                "challenge": cloud_challenge.challenge,
                "purpose": cloud_challenge.purpose.value,
                "destination": cloud_challenge.destination,
                "scopes": cloud_challenge.scopes,
                "expiresAt": cloud_challenge.expires_at.isoformat(),
            }

        ui_root = Path(args.ui_root) if args.ui_root else Path.cwd() / "ui" / "approval"
        if not (ui_root / "index.html").is_file() or not (ui_root / "dist" / "main.js").is_file():
            packaged = Path(str(importlib.resources.files("adk_harness"))) / "ui" / "approval"
            if (packaged / "index.html").is_file() and (packaged / "dist" / "main.js").is_file():
                ui_root = packaged
            else:
                raise GoogleAuthError(
                    "approval UI assets are missing; run npm ci --prefix ui/approval "
                    "and npm run build --prefix ui/approval"
                )
        bridge = LocalApprovalBridge(
            session=session,
            ui_root=ui_root,
            bootstrap=lambda: bootstrap,
            firebase_binding=firebase_binding,
            cloud_grant_consent=cloud_consent,
            setup_confirmation=setup_confirmation,
            cloud_grant_challenge=cloud_challenge,
            workflow_preview=sync_callbacks.get("workflow_preview"),
            workflow_consent=sync_callbacks.get("workflow_consent"),
            workflow_ack=sync_callbacks.get("workflow_ack"),
            workflow_reconcile=sync_callbacks.get("workflow_reconcile"),
            workflow_recovery=sync_callbacks.get("workflow_recovery"),
            workflow_config=workflow_value,
        )
        bridge.start()
        session.open()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        return 0
    except (GoogleAuthError, OSError, ValueError):
        print("trusted approval UI could not be started", file=sys.stderr)
        return 1
    finally:
        if bridge is not None:
            bridge.stop()


def _readiness(args: argparse.Namespace) -> int:
    """Print a truthful offline/read-only runtime readiness report."""
    from adk_harness.cloud.readiness import RuntimeReadinessVerifier

    try:
        handoff = json.loads(Path(args.handoff).read_text(encoding="utf-8"))
        selected = json.loads(Path(args.select_project).read_text(encoding="utf-8"))
        if not isinstance(handoff, dict) or not isinstance(selected, dict):
            raise ValueError("readiness inputs must be JSON objects")
        report = RuntimeReadinessVerifier(handoff, selected).verify()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"readiness inputs could not be loaded: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report.to_dict(), sort_keys=True))
    return 0 if report.ready else 1


def _install_plugin(args: argparse.Namespace) -> int:
    """Copy the packaged Antigravity assets into the local plugin directory."""
    source = Path(str(importlib.resources.files("adk_harness"))) / "plugins" / "antigravity"
    if not source.is_dir():
        # An editable checkout keeps the native assets outside the package.
        source = Path(__file__).resolve().parents[3] / "plugins" / "antigravity"
    if not source.is_dir():
        print("the packaged Antigravity plugin is missing", file=sys.stderr)
        return 2
    default = Path.home() / ".gemini" / "config" / "plugins" / "adk-harness"
    destination = Path(args.plugin_dir).expanduser() if args.plugin_dir else default
    try:
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination)
    except OSError as exc:
        print(f"the plugin could not be installed: {exc}", file=sys.stderr)
        return 2
    print(f"installed: {destination}")
    for path in sorted(destination.rglob("*")):
        if path.is_file():
            print(f"  {path.relative_to(destination)}")
    outcome = _register_hooks(args, destination)
    return outcome or _register_mcp_server(args)


def _register_hooks(args: argparse.Namespace, destination: Path) -> int:
    """Install the Stop hook that waits while somebody answers a card."""
    source = destination / "hooks" / "hooks.json"
    script = destination / "hooks" / "await_approval.py"
    if not source.is_file() or not script.is_file():
        return 0
    script.chmod(0o755)
    default = Path.home() / ".gemini" / "config" / "hooks.json"
    path = Path(args.hooks_config).expanduser() if args.hooks_config else default
    try:
        config = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, json.JSONDecodeError) as exc:
        print(f"the hooks configuration could not be read: {exc}", file=sys.stderr)
        return 2
    if not isinstance(config, dict):
        print("the hooks configuration is not a JSON object", file=sys.stderr)
        return 2
    ours = json.loads(source.read_text(encoding="utf-8").replace("PLUGIN_DIR", str(destination)))
    for event, entries in ours.items():
        existing = [
            entry
            for entry in config.get(event, [])
            if "await_approval.py" not in json.dumps(entry)
        ]
        config[event] = existing + entries
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"the hooks configuration could not be written: {exc}", file=sys.stderr)
        return 2
    print(f"hooked: {path}")
    return 0


def _register_mcp_server(args: argparse.Namespace) -> int:
    """Add this server to Antigravity's MCP configuration, keeping the rest."""
    default = Path.home() / ".gemini" / "config" / "mcp_config.json"
    path = Path(args.mcp_config).expanduser() if args.mcp_config else default
    try:
        config = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, json.JSONDecodeError) as exc:
        print(f"the MCP configuration could not be read: {exc}", file=sys.stderr)
        return 2
    if not isinstance(config, dict):
        print("the MCP configuration is not a JSON object", file=sys.stderr)
        return 2
    servers = config.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
    entry: dict[str, Any] = {
        "command": sys.executable,
        "args": ["-m", "adk_harness", "mcp"],
    }
    # Antigravity starts the server itself, so the client configuration has to
    # travel with the entry rather than through the shell.
    environment: dict[str, str] = {}
    client_config = args.client_config or os.environ.get("ADK_HARNESS_GOOGLE_CLIENT_CONFIG")
    if client_config:
        environment["ADK_HARNESS_GOOGLE_CLIENT_CONFIG"] = str(
            Path(client_config).expanduser().resolve()
        )
    # An administrator sets this once and every machine writes to one trail.
    project = args.gcp_project or os.environ.get("GOOGLE_CLOUD_PROJECT")
    if project:
        environment["GOOGLE_CLOUD_PROJECT"] = project
    if environment:
        entry["env"] = environment
    servers["adk-harness"] = entry
    config["mcpServers"] = servers
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"the MCP configuration could not be written: {exc}", file=sys.stderr)
        return 2
    print(f"registered: {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Local Google Antigravity workspace integration"
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=(
            "doctor",
            "status",
            "login",
            "logout",
            "ui",
            "onboard",
            "readiness",
            "install-plugin",
            "mcp",
        ),
        default="doctor",
    )
    parser.add_argument(
        "--purpose",
        choices=tuple(purpose.value for purpose in CredentialPurpose),
        default=CredentialPurpose.PROVISIONING.value,
    )
    parser.add_argument("--scope", action="append")
    parser.add_argument("--client-config")
    parser.add_argument("--subject")
    parser.add_argument("--firebase-config")
    parser.add_argument("--cloud-destination")
    parser.add_argument("--workspace-scope", action="append")
    parser.add_argument("--ui-root")
    parser.add_argument("--workflow-config", help="trusted local workflow configuration JSON")
    parser.add_argument("--outbox", help="durable local SQLite outbox path")
    parser.add_argument("--handoff", help="approved terraform_handoff JSON for readiness")
    parser.add_argument("--select-project", help="verified select_project checkpoint JSON")
    parser.add_argument("--plugin-dir", help="destination for install-plugin")
    parser.add_argument("--mcp-config", help="Antigravity mcp_config.json to register in")
    parser.add_argument("--gcp-project", help="Google Cloud project holding the audit ledger")
    parser.add_argument("--hooks-config", help="Antigravity hooks.json to register in")
    args = parser.parse_args(argv)
    if args.command == "doctor":
        return asyncio.run(_doctor())
    if args.command == "status":
        return _status(args.client_config, args.subject)
    if args.command == "login":
        return _login(args)
    if args.command == "logout":
        return _logout(args)
    if args.command in {"ui", "onboard"}:
        return _ui(args)
    if args.command == "mcp":
        from adk_harness.workspace.mcp_stdio import serve

        return serve(lambda: _build_auth(args.client_config))
    if args.command == "install-plugin":
        return _install_plugin(args)
    if args.command == "readiness":
        if not args.handoff or not args.select_project:
            parser.error("readiness requires --handoff and --select-project")
        return _readiness(args)
    return 1
