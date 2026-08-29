import json
import os
import shutil
import subprocess
from pathlib import Path
from textwrap import dedent

import pytest

ROOT = Path(__file__).parents[2]


def _npm_argv(*arguments: str) -> list[str]:
    """Invoke npm through node so Windows never needs a shell."""
    if os.name != "nt":
        return ["npm", *arguments]
    node = shutil.which("node.exe") or shutil.which("node")
    if node is None:
        pytest.skip("node is required for package installation test")
    npm_wrapper = shutil.which("npm.cmd") or shutil.which("npm")
    if npm_wrapper is None:
        pytest.skip("npm is required for package installation test")
    npm_cli = Path(npm_wrapper).resolve().parent / "node_modules" / "npm" / "bin" / "npm-cli.js"
    if not npm_cli.is_file():
        pytest.skip("npm-cli.js is required for package installation test")
    return [node, str(npm_cli), *arguments]


def test_npm_manifest_exposes_supported_local_launcher() -> None:
    manifest = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert manifest["bin"]["adk-harness"] == "bin/adk-harness.js"
    assert "infra/gcp/main.tf" in manifest["files"]
    assert (ROOT / "infra" / "gcp" / "main.tf").is_file()
    assert (ROOT / "bin" / "adk-harness.js").is_file()
    assert not (ROOT / "plugins" / "adk-harness").exists()


def _run_launcher_with_stub(
    launcher: Path, tmp_path: Path, *arguments: str
) -> subprocess.CompletedProcess[str]:
    """Load the real launcher while replacing only its child-process boundary."""
    capture = tmp_path / "spawn.json"
    wrapper = tmp_path / "wrapper.js"
    capture_json = json.dumps(str(capture))
    launcher_json = json.dumps(str(launcher))
    wrapper.write_text(
        dedent(
            f"""
            const fs = require('node:fs');
            const childProcess = require('node:child_process');
            childProcess.spawnSync = (command, args, options) => {{
              fs.writeFileSync({capture_json}, JSON.stringify({{command, args, options}}));
              return {{status: 23}};
            }};
            process.argv = ['node', {launcher_json}, ...process.argv.slice(2)];
            require({launcher_json});
            """
        ),
        encoding="utf-8",
    )
    return subprocess.run(
        ["node", str(wrapper), *arguments],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def test_launcher_uses_safe_argv_and_preserves_cwd(tmp_path: Path) -> None:
    launcher = ROOT / "bin" / "adk-harness.js"
    result = _run_launcher_with_stub(launcher, tmp_path, "an argument; &", "folder with spaces")

    assert result.returncode == 23
    invocation = json.loads((tmp_path / "spawn.json").read_text(encoding="utf-8"))
    assert invocation["args"] == [
        "tool",
        "run",
        "--python",
        "3.12",
        "--from",
        str(ROOT),
        "adk-harness",
        "an argument; &",
        "folder with spaces",
    ]
    assert invocation["options"]["cwd"] == str(tmp_path)
    assert invocation["options"]["shell"] is False


def test_launcher_reports_missing_uv(tmp_path: Path) -> None:
    launcher = ROOT / "bin" / "adk-harness.js"
    wrapper = tmp_path / "missing-uv-wrapper.js"
    launcher_json = json.dumps(str(launcher))
    wrapper.write_text(
        dedent(
            f"""
            const childProcess = require('node:child_process');
            childProcess.spawnSync = () => ({{ error: Object.assign(
              new Error('missing'), {{ code: 'ENOENT' }}
            ) }});
            require({launcher_json});
            """
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        ["node", str(wrapper)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 1
    assert "adk-harness needs uv" in result.stderr


@pytest.mark.skipif(
    shutil.which("npm") is None, reason="npm is required for package installation test"
)
def test_packed_npm_install_exposes_executable(tmp_path: Path) -> None:
    package_dir = tmp_path / "package"
    prefix = tmp_path / "prefix"
    package_dir.mkdir()
    subprocess.run(
        _npm_argv(
            "pack",
            "--pack-destination",
            str(package_dir),
            "--ignore-scripts",
            "--no-audit",
            "--no-fund",
        ),
        cwd=ROOT,
        check=True,
        timeout=30,
        capture_output=True,
        text=True,
    )
    tarball = next(package_dir.glob("adk-harness-*.tgz"))
    subprocess.run(
        _npm_argv(
            "install",
            "--offline",
            "--ignore-scripts",
            "--no-audit",
            "--no-fund",
            "--prefix",
            str(prefix),
            str(tarball),
        ),
        check=True,
        timeout=30,
        capture_output=True,
        text=True,
    )
    installed = prefix / "node_modules" / "adk-harness" / "bin" / "adk-harness.js"
    assert installed.is_file()

    result = _run_launcher_with_stub(installed, tmp_path, "--help")
    assert result.returncode == 23
    invocation = json.loads((tmp_path / "spawn.json").read_text(encoding="utf-8"))
    from_index = invocation["args"].index("--from")
    assert invocation["args"][from_index + 1] == str(installed.parent.parent.resolve())


def test_launcher_installs_the_plugin_without_python(tmp_path: Path) -> None:
    """The Node path must copy the assets without ever reaching for uv."""
    destination = tmp_path / "adk-harness"
    result = _run_launcher_with_stub(
        ROOT / "bin" / "adk-harness.js",
        tmp_path,
        "install-plugin",
        "--plugin-dir",
        str(destination),
    )

    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "spawn.json").exists()
    assert (destination / "plugin.json").is_file()
    assert (destination / "skills" / "governed-workspace" / "SKILL.md").is_file()
    assert str(destination) in result.stdout


def test_launcher_rejects_a_plugin_dir_without_a_path(tmp_path: Path) -> None:
    result = _run_launcher_with_stub(
        ROOT / "bin" / "adk-harness.js", tmp_path, "install-plugin", "--plugin-dir"
    )

    assert result.returncode == 2
    assert "--plugin-dir needs a path" in result.stderr
