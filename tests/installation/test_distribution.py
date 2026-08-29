from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

from tests.check_distribution import (
    SDIST_RELATIVE_MEMBERS,
    WHEEL_MEMBERS,
    check,
    is_forbidden_archive_member,
    is_forbidden_credential_member,
)
from tests.installation.test_npm_package import _npm_argv

ROOT = Path(__file__).parents[2]


@pytest.mark.parametrize(
    "member",
    (
        "project/credentials.json",
        "project/client_secret_123.json",
        "project/token.json",
        "project/application_default_credentials.json",
        "project/service-account-prod.json",
        "project/service_account_prod.json",
        "project/.credentials/oauth.json",
        "project/credentials/oauth.json",
        "project/.config/gcloud/access_tokens.db",
        "project/tokens/session.json",
    ),
)
def test_credential_member_names_are_rejected(member: str) -> None:
    assert is_forbidden_credential_member(member)


@pytest.mark.parametrize(
    "member",
    (
        "src/adk_harness/auth/credentials.py",
        "plugins/antigravity/plugin.json",
        "LICENSE",
        "docs/credentials-guide.md",
        "examples/data/example.json",
    ),
)
def test_valid_source_and_required_assets_are_not_rejected(member: str) -> None:
    assert not is_forbidden_credential_member(member)


@pytest.mark.parametrize("member", ("mcp_server.py", "mcp_config.json"))
def test_retired_mcp_artifact_names_are_rejected(member: str) -> None:
    assert is_forbidden_archive_member(f"project/{member}")


def test_npmignore_covers_the_same_known_credential_outputs() -> None:
    npmignore = (ROOT / ".npmignore").read_text(encoding="utf-8")
    for pattern in (
        "**/credentials.json",
        "**/client_secret*.json",
        "**/token.json",
        "**/application_default_credentials.json",
        "**/service-account*.json",
        "**/service_account*.json",
        "**/.credentials/",
        "**/credentials/",
        "**/.tokens/",
        "**/tokens/",
        "**/.config/gcloud/",
    ):
        assert pattern in npmignore


def test_npm_pack_excludes_synthetic_credentials_from_native_assets(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture"
    shutil.copytree(
        ROOT,
        fixture,
        ignore=shutil.ignore_patterns(
            ".git",
            ".venv",
            ".pytest_cache",
            ".ruff_cache",
            ".superpowers",
            "__pycache__",
            "node_modules",
            "seeded-dist",
            ".pytest-task*-temp",
        ),
    )
    native = fixture / "plugins" / "antigravity"
    (native / "credentials.json").write_text("{}", encoding="utf-8")
    (native / "skills" / "governed-workspace" / "token.json").write_text(
        "{}", encoding="utf-8"
    )

    result = subprocess.run(
        _npm_argv(
            "pack",
            "--dry-run",
            "--json",
            "--offline",
            "--ignore-scripts",
            "--no-audit",
            "--no-fund",
        ),
        cwd=fixture,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    members = {entry["path"] for entry in json.loads(result.stdout)[0]["files"]}
    assert "plugins/antigravity/plugin.json" in members
    assert "plugins/antigravity/credentials.json" not in members
    assert "plugins/antigravity/skills/governed-workspace/token.json" not in members


def test_real_seeded_build_excludes_credentials_from_wheel_and_sdist(tmp_path: Path) -> None:
    uv = shutil.which("uv") or shutil.which("uv.exe")
    if uv is None:
        pytest.skip("uv is required for the seeded archive build probe")

    fixture = tmp_path / "fixture"
    shutil.copytree(
        ROOT,
        fixture,
        ignore=shutil.ignore_patterns(
            ".git",
            ".venv",
            ".pytest_cache",
            ".ruff_cache",
            ".superpowers",
            "__pycache__",
            "node_modules",
            "seeded-dist",
            ".pytest-task*-temp",
        ),
    )
    seeds = (
        fixture / "plugins" / "antigravity" / "credentials.json",
        fixture / "plugins" / "antigravity" / "client_secret-seeded.json",
        fixture / "docs" / "token.json",
        fixture / "examples" / "application_default_credentials.json",
        fixture / "src" / "adk_harness" / "credentials.json",
    )
    for seed in seeds:
        seed.parent.mkdir(parents=True, exist_ok=True)
        seed.write_text("{}", encoding="utf-8")
    source_module = fixture / "src" / "adk_harness" / "auth" / "credentials.py"
    source_module.parent.mkdir(parents=True, exist_ok=True)
    source_module.write_text("# valid source module name\n", encoding="utf-8")

    output_dir = fixture / "seeded-dist"
    subprocess.run(
        [
            uv,
            "build",
            "--offline",
            "--no-build-isolation",
            "--python",
            sys.executable,
            "--sdist",
            "--wheel",
            "--out-dir",
            str(output_dir),
        ],
        cwd=fixture,
        env={**os.environ, "UV_OFFLINE": "1"},
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    archives = (*output_dir.glob("*.whl"), *output_dir.glob("*.tar.gz"))
    assert len(archives) == 2
    for archive in archives:
        check(archive)
        if archive.suffix == ".whl":
            names = zipfile.ZipFile(archive).namelist()
        else:
            names = tarfile.open(archive).getnames()
        assert not any(is_forbidden_credential_member(name) for name in names)
        assert any(name.endswith("auth/credentials.py") for name in names)
        assert any(name.endswith("ui/approval/index.html") for name in names)
        assert any(name.endswith("ui/approval/dist/main.js") for name in names)


def _write_wheel(path: Path, extra: str | None = None) -> None:
    members = [*WHEEL_MEMBERS, "adk_harness-0.1.0.dist-info/licenses/LICENSE"]
    if extra:
        members.append(extra)
    with zipfile.ZipFile(path, "w") as archive:
        for member in members:
            archive.writestr(member, "fixture")


def _write_sdist(path: Path, extra: str | None = None) -> None:
    prefix = "adk_harness-0.1.0"
    members = [f"{prefix}{member}" for member in SDIST_RELATIVE_MEMBERS]
    members.extend((f"{prefix}/LICENSE", f"{prefix}/pyproject.toml"))
    if extra:
        members.append(f"{prefix}/{extra}")
    with tarfile.open(path, "w:gz") as archive:
        for member in members:
            info = tarfile.TarInfo(member)
            info.size = len(b"fixture")
            archive.addfile(info, io.BytesIO(b"fixture"))


def test_archive_checker_accepts_required_assets_and_source_credentials_module(
    tmp_path: Path,
) -> None:
    wheel = tmp_path / "valid.whl"
    sdist = tmp_path / "valid.tar.gz"
    _write_wheel(wheel, "adk_harness/auth/credentials.py")
    _write_sdist(sdist, "src/adk_harness/auth/credentials.py")

    check(wheel)
    check(sdist)


@pytest.mark.parametrize("archive_kind", ("wheel", "sdist"))
@pytest.mark.parametrize(
    "member",
    (
        "credentials.json",
        ".credentials/token.json",
        "client_secret.json",
        "mcp_server.py",
        "mcp_config.json",
    ),
)
def test_archive_checker_rejects_credential_members(
    tmp_path: Path, archive_kind: str, member: str
) -> None:
    archive = tmp_path / ("invalid.whl" if archive_kind == "wheel" else "invalid.tar.gz")
    if archive_kind == "wheel":
        _write_wheel(archive, f"project/{member}")
    else:
        _write_sdist(archive, f"project/{member}")

    with pytest.raises(AssertionError, match=r"credential|token|client_secret|mcp"):
        check(archive)
