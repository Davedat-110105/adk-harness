"""`adk-harness setup` — install the Antigravity plugin and say what is missing.

    adk-harness setup            check everything and install the plugin
    adk-harness setup --check    check only, change nothing

Written because the manual instructions were four steps and every one of them
failed silently in a different way: a plugin copied to the wrong directory, a
token missing a scope, a project id unset. Each produced "the tools are not
there" with no clue which step was wrong.

This does the parts that can be automated and, for the part that cannot, prints
the exact command with your values already filled in.

The part that cannot be automated
---------------------------------
Google will not issue Calendar or Gmail scopes to `gcloud`'s own OAuth client,
so you need your own — which means a Cloud project, a consent screen, and
yourself on its test-user list. That is a browser task, roughly three minutes,
and no flag removes it for a personal account.

It disappears entirely once someone publishes a verified app: then a user signs
in and consents, with no Cloud project of their own. That is the difference
between this and a product, and it is worth being plain about.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

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
    for candidate in (here.parent / "plugin", here.parents[2] / "plugin"):
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
    if PLUGIN_DIR.exists():
        shutil.rmtree(PLUGIN_DIR)
    PLUGIN_DIR.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, PLUGIN_DIR)

    # The shipped config is portable; the installed copy must point at the
    # interpreter that actually has adk_harness importable, which is rarely
    # whatever `python` resolves to inside Antigravity.
    config = PLUGIN_DIR / "mcp_config.json"
    data = json.loads(config.read_text())
    entry = data["mcpServers"]["adk-harness"]
    entry["command"] = sys.executable
    env = entry.setdefault("env", {})
    env["ADK_HARNESS_WORKSPACE"] = str(Path.cwd())
    env["ADK_PRECEDENTS"] = str(Path.home() / ".adk-harness-precedents.db")
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if project:
        env["GOOGLE_CLOUD_PROJECT"] = project
    else:
        env.pop("GOOGLE_CLOUD_PROJECT", None)
    config.write_text(json.dumps(data, indent=2) + "\n")
    return True, f"installed to {PLUGIN_DIR}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="report only; install nothing"
    )
    args = parser.parse_args()

    print("adk-harness setup\n")
    checks = [
        ("gcloud", _check_gcloud()),
        ("project", _check_project()),
        ("scopes", _check_scopes()),
    ]
    for name, (passed, detail) in checks:
        print(f"{OK if passed else NO}{name:10} {detail}")

    if not args.check:
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


if __name__ == "__main__":
    raise SystemExit(main())
