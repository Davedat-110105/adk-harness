"""Setup, diagnostics, adapter scaffolding, and MCP serving commands."""

from __future__ import annotations

import argparse
import asyncio
import json
import keyword
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from adk_harness.coding.registry import default_registry

__all__ = ["main"]

PLUGIN_DIR = Path.home() / ".gemini/config/plugins/adk-harness"
SCOPES = {
    "calendar": "https://www.googleapis.com/auth/calendar.events",
    "gmail": "https://www.googleapis.com/auth/gmail.compose",
}

OK = "  ok    "
NO = "  needs "


def _run(*args: str) -> tuple[int, str]:
    try:
        done = subprocess.run(
            args, capture_output=True, text=True, timeout=60, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    # stdout when it worked, stderr when it did not — the previous one-liner
    # chained `and` inside `or` and had to be read twice to be believed.
    output = done.stdout if done.returncode == 0 else done.stderr
    return done.returncode, (output or "").strip()


def _plugin_source() -> Path | None:
    """The bundled plugin directory, whether installed or run from a checkout."""
    here = Path(__file__).resolve()
    for candidate in (
        here.parents[1] / "plugins" / "antigravity",
        here.parents[3] / "plugins" / "antigravity",
    ):
        if (candidate / "plugin.json").exists():
            return candidate
    return None


def _check_gcloud() -> tuple[bool, str]:
    if shutil.which("gcloud") is None:
        return False, "install the Google Cloud CLI: https://cloud.google.com/sdk"
    return True, "gcloud is installed"


def _check_project() -> tuple[bool, str]:
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if project:
        return True, f"project {project} (from GOOGLE_CLOUD_PROJECT)"
    code, out = _run("gcloud", "config", "get-value", "project")
    if code == 0 and out and out != "(unset)":
        return True, f"project {out} (from gcloud config)"
    return False, "set one: gcloud config set project YOUR_PROJECT_ID"


def _check_scopes() -> tuple[bool, str]:
    """Ask Google what the token carries, not the credentials what they believe."""
    try:
        import google.auth
        import google.auth.transport.requests
    except ImportError:
        return False, 'pip install "adk-harness[google-workspace]"'

    try:
        credentials, _ = google.auth.default(scopes=list(SCOPES.values()))
        request = google.auth.transport.requests.Request()
        credentials.refresh(request)
        response = request(
            url=(
                "https://oauth2.googleapis.com/tokeninfo?access_token="
                f"{credentials.token}"
            ),
            method="GET",
        )
    except Exception as exc:  # no ADC at all
        return False, f"no usable credentials ({type(exc).__name__}); see below"

    if response.status != 200:
        return True, "service-account credentials (scopes not introspectable)"

    granted = set(str(json.loads(response.data).get("scope", "")).split())
    missing = [name for name, scope in SCOPES.items() if scope not in granted]
    if not missing:
        return True, "calendar and gmail scopes present"
    return False, f"token is missing: {', '.join(missing)}"


def _login_command() -> str:
    scopes = ",".join(
        [
            "openid",
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/cloud-platform",
            *SCOPES.values(),
        ]
    )
    return (
        "gcloud auth application-default login \\\n"
        "    --client-id-file=$HOME/Downloads/client_secret.json \\\n"
        f"    --scopes={scopes}"
    )


def _install_plugin() -> tuple[bool, str]:
    source = _plugin_source()
    if source is None:
        return False, "cannot find the bundled plugin directory"
    PLUGIN_DIR.parent.mkdir(parents=True, exist_ok=True)
    backup = PLUGIN_DIR.with_name(f"{PLUGIN_DIR.name}.backup")
    if backup.exists() or backup.is_symlink():
        return False, f"backup already exists at {backup}; remove it after review"
    staging = Path(tempfile.mkdtemp(prefix=f".{PLUGIN_DIR.name}-", dir=PLUGIN_DIR.parent))
    try:
        shutil.copytree(source, staging, dirs_exist_ok=True)
        config = staging / "mcp_config.json"
        data = json.loads(config.read_text())
        entry = data["mcpServers"]["adk-harness"]
        entry["command"] = sys.executable
        env = entry.setdefault("env", {})
        env["ADK_HARNESS_WORKSPACE"] = str(Path.cwd())
        env.pop("ADK_PRECEDENTS", None)
        project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        if project:
            env["GOOGLE_CLOUD_PROJECT"] = project
        else:
            env.pop("GOOGLE_CLOUD_PROJECT", None)
        config.write_text(json.dumps(data, indent=2) + "\n")
        if PLUGIN_DIR.exists() or PLUGIN_DIR.is_symlink():
            PLUGIN_DIR.rename(backup)
        try:
            staging.rename(PLUGIN_DIR)
        except Exception:
            if backup.exists() or backup.is_symlink():
                backup.rename(PLUGIN_DIR)
            raise
    except Exception as exc:
        if staging.exists():
            shutil.rmtree(staging)
        return False, f"could not install plugin safely: {type(exc).__name__}: {exc}"
    return True, f"installed to {PLUGIN_DIR}"


def _setup(check: bool) -> int:

    print("adk-harness setup\n")
    checks = [
        ("gcloud", _check_gcloud()),
        ("project", _check_project()),
        ("scopes", _check_scopes()),
    ]
    for name, (passed, detail) in checks:
        print(f"{OK if passed else NO}{name:10} {detail}")

    if not check:
        passed, detail = _install_plugin()
        print(f"{OK if passed else NO}{'plugin':10} {detail}")
        checks.append(("plugin", (passed, detail)))

    blocked = [name for name, (passed, _) in checks if not passed]
    if not blocked:
        print("\nRestart Antigravity. The Calendar and Gmail tools will be there.")
        return 0

    print(f"\nNot ready yet: {', '.join(blocked)}.")
    if "scopes" in blocked:
        print(
            "\nGoogle refuses Calendar and Gmail scopes to gcloud's shared OAuth\n"
            "client, so you need your own. Once, in the Cloud console:\n\n"
            "  1. console.cloud.google.com/auth/overview — create the consent\n"
            "     screen, User type External, leave it in Testing\n"
            "  2. console.cloud.google.com/auth/audience — add your own email\n"
            "     under Test users. Skipping this is what causes 'Access blocked'\n"
            "  3. console.cloud.google.com/auth/clients — create an OAuth client,\n"
            "     type Desktop app, and download the JSON\n\n"
            "Then run:\n\n"
            f"{_login_command()}\n\n"
            "Google drops scopes it will not grant rather than failing the login,\n"
            "so check the consent screen actually lists Calendar and Gmail."
        )
    return 1


def _doctor() -> int:
    """Read-only diagnostics for every built-in and installed extension."""
    async def inspect() -> tuple:
        registry = default_registry()
        return await registry.discover_all()

    specs = asyncio.run(inspect())
    print("adk-harness doctor\n")
    ready = False
    for spec in specs:
        display_detail = spec.detail or ""
        if spec.available:
            if spec.id == "codex":
                logged_in, detail = _codex_login_status()
                status = "ready" if logged_in else "credentials missing"
                action = "" if logged_in else "run `codex login`, then rerun doctor"
                if not logged_in:
                    display_detail = detail
                else:
                    ready = True
            else:
                status, action = "discovery-only (credentials unverified)", ""
        else:
            detail = (spec.detail or "unknown reason").lower()
            if "server" in detail or "connect" in detail or "health" in detail:
                status = "server unreachable"
                action = (
                    "run `opencode serve --port 4096`, then rerun doctor"
                    if spec.id == "opencode"
                    else "start the harness server, then rerun doctor"
                )
            elif "credential" in detail or "auth" in detail or "token" in detail:
                status = "credentials missing"
                action = (
                    "run `codex login`, then rerun doctor"
                    if spec.id == "codex"
                    else "configure the harness credentials, then rerun doctor"
                )
            elif "not installed" in detail or "not found" in detail or "could not" in detail:
                status, action = "missing binary/package", _next_action(spec.id)
            else:
                status, action = "uncertain", "inspect the detail and rerun doctor"
        print(f"{status:22} {spec.id:14} {display_detail}")
        if action:
            print(f"{'':22} {'':14} next: {action}")
    return 0 if ready else 1


def _codex_login_status() -> tuple[bool, str]:
    """Check Codex auth without exposing its output or reading credentials."""
    code, _ = _run("codex", "login", "status")
    if code == 0:
        return True, "codex login status reported an active login"
    return False, "codex login status failed; credentials may be missing"


def _next_action(harness_id: str) -> str:
    return {
        "codex": "install Codex CLI, then run `codex login`",
        "claude_code": (
            "install with `pip install 'adk-harness[claude-code]'` and ensure "
            "`claude` is on PATH"
        ),
        "opencode": "install OpenCode, then run `opencode serve --port 4096`",
        "antigravity": "install with `pip install 'adk-harness[antigravity]'`",
    }.get(harness_id, "install the extension package, then rerun `adk-harness doctor`")


_ADAPTER_TEMPLATE = '''"""Minimal offline adapter scaffold for {name}."""
from collections.abc import AsyncIterator
from adk_harness.coding.protocol import HarnessSpec, HarnessTurn


class {class_name}:
    def __init__(self) -> None:
        self.spec = HarnessSpec(id="{name}", version="0.1", capabilities=("text",), available=True)

    async def discover(self) -> HarnessSpec:
        return self.spec

    async def aclose(self) -> None:
        return None

    async def _turns(self, prompt: str) -> AsyncIterator[HarnessTurn]:
        yield HarnessTurn(kind="text", text=prompt, raw=prompt)

    def run(
        self, prompt: str, *, cwd: str, session_id: str | None = None
    ) -> AsyncIterator[HarnessTurn]:
        return self._turns(prompt)
'''


_TEST_TEMPLATE = '''import pytest
from adk_harness.coding.adapters.{name} import {class_name}


@pytest.mark.asyncio
async def test_{name}_echo() -> None:
    turns = [turn async for turn in {class_name}().run("hello", cwd=".")]
    assert turns[0].kind == "text"
    assert turns[0].text == "hello"
'''


def _new_adapter(name: str) -> int:
    if (
        not name.isascii()
        or not name.isidentifier()
        or not name.islower()
        or name.startswith("_")
        or keyword.iskeyword(name)
    ):
        print("adapter name must be an ASCII lowercase Python identifier", file=sys.stderr)
        return 2
    root = Path.cwd()
    adapter = root / "src" / "adk_harness" / "coding" / "adapters" / f"{name}.py"
    test = root / "tests" / "coding" / "adapters" / f"test_{name}.py"
    if adapter.exists() or test.exists() or adapter.is_symlink() or test.is_symlink():
        print("refusing to overwrite existing adapter or test", file=sys.stderr)
        return 2
    if any(_symlink_ancestor(path, root) for path in (adapter, test)):
        print("refusing to write through a symlinked directory", file=sys.stderr)
        return 2
    root_resolved = root.resolve()
    if not adapter.resolve().is_relative_to(root_resolved) or not test.resolve().is_relative_to(
        root_resolved
    ):
        print("refusing to write outside the current project", file=sys.stderr)
        return 2
    class_name = "".join(part.title() for part in name.split("_")) + "Harness"
    adapter.parent.mkdir(parents=True, exist_ok=True)
    test.parent.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    try:
        for path, content in (
            (adapter, _ADAPTER_TEMPLATE.format(name=name, class_name=class_name)),
            (test, _TEST_TEMPLATE.format(name=name, class_name=class_name)),
        ):
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            with os.fdopen(fd, "w") as output:
                output.write(content)
            created.append(path)
    except FileExistsError:
        for path in created:
            path.unlink(missing_ok=True)
        print("refusing to overwrite existing adapter or test", file=sys.stderr)
        return 2
    print(f"created {adapter}\ncreated {test}\nrun: pytest {test}")
    return 0


def _symlink_ancestor(path: Path, root: Path) -> bool:
    current = root
    for part in path.relative_to(root).parts[:-1]:
        current /= part
        if current.is_symlink():
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Setup, diagnose, and serve adk-harness.")
    subparsers = parser.add_subparsers(dest="command")
    setup_parser = subparsers.add_parser("setup", help="check and optionally install the plugin")
    setup_parser.add_argument("--check", action="store_true", help="report only; install nothing")
    subparsers.add_parser("doctor", help="read-only harness diagnostics")
    new_parser = subparsers.add_parser("new-adapter", help="create a minimal adapter scaffold")
    new_parser.add_argument("name")
    subparsers.add_parser("serve", help="run the MCP server")
    # Retain the old explicit --check flag; a bare invocation only shows help.
    parser.add_argument("--check", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.command is None:
        if args.check:
            return _setup(True)
        parser.print_help()
        return 0
    if args.command == "setup":
        return _setup(getattr(args, "check", False))
    if args.command == "doctor":
        return _doctor()
    if args.command == "serve":
        from adk_harness.mcp.server import main as serve

        serve()
        return 0
    return _new_adapter(args.name)


if __name__ == "__main__":
    raise SystemExit(main())
