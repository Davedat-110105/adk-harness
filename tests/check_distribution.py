"""Check release archives: ``python tests/check_distribution.py dist/*``."""

from __future__ import annotations

import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

WHEEL_MEMBERS = (
    "adk_harness/cli/main.py",
    "adk_harness/governance/content_armor.py",
    "adk_harness/governance/stores.py",
    "adk_harness/integrations/antigravity.py",
    "adk_harness/plugins/antigravity/plugin.json",
    "adk_harness/plugins/antigravity/README.md",
    "adk_harness/plugins/antigravity/rules/governance.md",
    "adk_harness/plugins/antigravity/skills/governed-workspace/SKILL.md",
    "adk_harness/workflow/models.py",
    "adk_harness/workflow/sync.py",
    "adk_harness/workflow/outbox.py",
    "adk_harness/cloud/readiness.py",
    "adk_harness/cloud/entrypoints.py",
    "adk_harness/ui/approval/index.html",
    "adk_harness/ui/approval/dist/main.js",
    "adk_harness/workspace/app.py",
)
SDIST_RELATIVE_MEMBERS = (
    "/src/adk_harness/cli/main.py",
    "/src/adk_harness/governance/content_armor.py",
    "/src/adk_harness/governance/stores.py",
    "/src/adk_harness/integrations/antigravity.py",
    "/plugins/antigravity/plugin.json",
    "/plugins/antigravity/README.md",
    "/plugins/antigravity/rules/governance.md",
    "/plugins/antigravity/skills/governed-workspace/SKILL.md",
    "/src/adk_harness/workflow/models.py",
    "/src/adk_harness/workflow/sync.py",
    "/src/adk_harness/workflow/outbox.py",
    "/src/adk_harness/cloud/readiness.py",
    "/src/adk_harness/cloud/entrypoints.py",
    "/ui/approval/index.html",
    "/ui/approval/src/main.ts",
    "/ui/approval/src/sync.ts",
    "/ui/approval/dist/main.js",
    "/src/adk_harness/workspace/app.py",
)

_CREDENTIAL_FILE_NAMES = {
    "credentials.json",
    "token.json",
    "application_default_credentials.json",
}
_CREDENTIAL_DIRECTORY_NAMES = {".credentials", "credentials", ".tokens", "tokens"}
_RETIRED_MEMBER_NAMES = {"mcp_server.py", "mcp_config.json"}


def is_forbidden_credential_member(name: str) -> bool:
    """Return whether an archive member has a known credential-shaped path.

    Filename rules are deliberately narrow and do not attempt to inspect file
    contents or reject every JSON file. The policy protects known local tooling
    outputs while permitting source modules such as ``auth/credentials.py``.
    """
    parts = [part.casefold() for part in PurePosixPath(name).parts]
    filename = parts[-1] if parts else ""
    if filename in _CREDENTIAL_FILE_NAMES:
        return True
    if filename.startswith("client_secret") and filename.endswith(".json"):
        return True
    if filename.startswith("service-account") and filename.endswith(".json"):
        return True
    if filename.startswith("service_account") and filename.endswith(".json"):
        return True
    if any(part in _CREDENTIAL_DIRECTORY_NAMES for part in parts[:-1]):
        return True
    return any(
        parts[index : index + 2] == [".config", "gcloud"]
        for index in range(len(parts) - 2)
    )


def is_forbidden_archive_member(name: str) -> bool:
    """Return whether a member is a known credential or retired artifact."""
    return is_forbidden_credential_member(name) or PurePosixPath(name).name in _RETIRED_MEMBER_NAMES


def check(path: Path) -> None:
    """Assert that one wheel or source archive is a safe supported release."""
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
        for member in WHEEL_MEMBERS:
            assert member in names, f"missing packaged asset or canonical module {member}"
    else:
        with tarfile.open(path) as archive:
            names = archive.getnames()
        project_root = next((name for name in names if name.endswith("/pyproject.toml")), "")
        assert project_root, "sdist is missing its project root"
        prefix = project_root.removesuffix("/pyproject.toml")
        for relative in SDIST_RELATIVE_MEMBERS:
            member = f"{prefix}{relative}"
            assert member in names, f"missing packaged asset or canonical module {member}"
    assert any(PurePosixPath(name).name == "LICENSE" for name in names), "missing license"
    for name in names:
        parts = PurePosixPath(name).parts
        assert not any(part.startswith(".env") or part == ".adk" for part in parts), name
        assert not any(
            part.endswith((".db", ".sqlite", ".sqlite3"))
            or ".db-" in part
            or ".sqlite-" in part
            or ".sqlite3-" in part
            for part in parts
        ), name
        assert ".superpowers" not in parts, name
        assert "plugins/adk-harness" not in "/".join(parts), name
        assert not is_forbidden_archive_member(name), name
        if "adk_harness" in parts:
            assert not any(part in {"coding", "mcp"} for part in parts), name
    print(f"{path.name}: canonical modules, native assets, license and exclusions verified")


if __name__ == "__main__":
    for argument in sys.argv[1:]:
        check(Path(argument))
