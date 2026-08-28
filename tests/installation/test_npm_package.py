from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
LAUNCHER = ROOT / "bin" / "adk-harness.js"


def test_npm_pack_contains_launcher_and_python_sources(tmp_path: Path) -> None:
    result = subprocess.run(
        ["npm", "pack", "--json", "--dry-run"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    files = {entry["path"] for entry in json.loads(result.stdout)[0]["files"]}
    assert "bin/adk-harness.js" in files
    assert "pyproject.toml" in files
    assert "src/adk_harness/__init__.py" in files
    assert "plugins/antigravity/plugin.json" in files
    assert "plugins/adk-harness/.codex-plugin/plugin.json" in files
    assert "plugins/adk-harness/.mcp.json" in files
    assert not any("__pycache__" in path for path in files)


def test_launcher_passes_project_and_arguments_to_uv(tmp_path: Path) -> None:
    capture = tmp_path / "args"
    fake_uv = tmp_path / "uv"
    fake_uv.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$CAPTURE\"\n"
        "printf '%s\\n' \"$PWD\" > \"$CWD_CAPTURE\"\nexit 17\n",
        encoding="utf-8",
    )
    fake_uv.chmod(fake_uv.stat().st_mode | stat.S_IXUSR)
    cwd_capture = tmp_path / "cwd"
    caller_cwd = tmp_path / "caller"
    caller_cwd.mkdir()
    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "CAPTURE": str(capture),
        "CWD_CAPTURE": str(cwd_capture),
    }

    result = subprocess.run(
        ["node", str(LAUNCHER), "doctor", "--help"],
        cwd=caller_cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 17
    args = capture.read_text(encoding="utf-8").splitlines()
    assert args[:7] == [
        "tool",
        "run",
        "--python",
        "3.12",
        "--from",
        f"{ROOT}[google-workspace]",
        "adk-harness",
    ]
    assert args[7:] == ["doctor", "--help"]
    assert cwd_capture.read_text(encoding="utf-8").strip() == str(caller_cwd)


def test_launcher_gives_actionable_message_when_uv_is_missing(tmp_path: Path) -> None:
    node = Path(shutil.which("node") or "/usr/bin/node")
    node_link = tmp_path / "node"
    node_link.symlink_to(node)
    env = {**os.environ, "PATH": str(tmp_path)}
    result = subprocess.run(
        [str(node_link), str(LAUNCHER), "--help"],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "needs uv" in result.stderr
    assert "docs.astral.sh/uv" in result.stderr


def test_packed_tarball_installs_in_a_temporary_prefix(tmp_path: Path) -> None:
    destination = tmp_path / "tarball"
    destination.mkdir()
    packed = json.loads(
        subprocess.run(
            ["npm", "pack", "--json", f"--pack-destination={destination}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )[0]["filename"]
    prefix = tmp_path / "prefix"
    subprocess.run(
        ["npm", "install", "--global", "--prefix", str(prefix), str(destination / packed)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert (prefix / "lib/node_modules/adk-harness/bin/adk-harness.js").is_file()


@pytest.mark.skipif(
    os.getenv("ADK_HARNESS_INSTALL_TEST") != "1", reason="opt-in: resolves runtime downloads"
)
def test_installed_launcher_help_with_real_uv(tmp_path: Path) -> None:
    destination = tmp_path / "tarball"
    destination.mkdir()
    packed = json.loads(
        subprocess.run(
            ["npm", "pack", "--json", f"--pack-destination={destination}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )[0]["filename"]
    prefix = tmp_path / "prefix"
    subprocess.run(
        ["npm", "install", "--global", "--prefix", str(prefix), str(destination / packed)],
        check=True,
        capture_output=True,
        text=True,
    )
    result = subprocess.run(
        [str(prefix / "bin/adk-harness"), "serve", "--help"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert "usage" in result.stdout.lower()
    assert "serve" in result.stdout.lower()
