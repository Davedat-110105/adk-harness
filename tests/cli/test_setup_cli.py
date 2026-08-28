import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from adk_harness import setup_cli
from adk_harness.coding.protocol import HarnessSpec
from adk_harness.coding.registry import HarnessRegistry


def test_dispatch_setup_check(monkeypatch) -> None:
    monkeypatch.setattr(setup_cli, "_setup", lambda check: 7 if check else 8)
    assert setup_cli.main(["setup", "--check"]) == 7
    assert setup_cli.main(["--check"]) == 7


def test_no_command_is_help_and_serve_routes_to_mcp(monkeypatch, capsys) -> None:
    from adk_harness.mcp import server

    def unexpected_setup(check):
        raise AssertionError("help must not install a plugin")

    calls = []
    monkeypatch.setattr(setup_cli, "_setup", unexpected_setup)
    monkeypatch.setattr(server, "main", lambda: calls.append("serve"))
    assert setup_cli.main([]) == 0
    assert "serve" in capsys.readouterr().out
    assert setup_cli.main(["serve"]) == 0
    assert calls == ["serve"]


def test_module_entry_points_preserve_failure_exit_code(tmp_path: Path) -> None:
    for module in ("adk_harness", "adk_harness.setup_cli"):
        result = subprocess.run(
            [sys.executable, "-m", module, "new-adapter", "not-a-python-name"],
            cwd=tmp_path,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 2


def test_doctor_is_read_only(monkeypatch, capsys) -> None:
    class Stub:
        spec = HarnessSpec(id="stub", version="1", available=False, detail="binary not found")

        async def discover(self):
            return self.spec

    monkeypatch.setattr(setup_cli, "default_registry", lambda: HarnessRegistry([Stub()]))
    assert setup_cli.main(["doctor"]) == 1
    assert "missing binary/package" in capsys.readouterr().out


def test_doctor_checks_codex_login_without_printing_subprocess_output(monkeypatch, capsys) -> None:
    class Stub:
        spec = HarnessSpec(id="codex", version="1", available=True)

        async def discover(self):
            return self.spec

    calls = []

    def fake_run(*args):
        calls.append(args)
        return 0, "Logged in as secret@example.com"

    monkeypatch.setattr(setup_cli, "default_registry", lambda: HarnessRegistry([Stub()]))
    monkeypatch.setattr(setup_cli, "_run", fake_run)
    assert setup_cli.main(["doctor"]) == 0
    output = capsys.readouterr().out
    assert calls == [("codex", "login", "status")]
    assert "secret@example.com" not in output
    assert "ready" in output


def test_doctor_reports_codex_credentials_missing(monkeypatch, capsys) -> None:
    class Stub:
        spec = HarnessSpec(id="codex", version="1", available=True)

        async def discover(self):
            return self.spec

    monkeypatch.setattr(setup_cli, "default_registry", lambda: HarnessRegistry([Stub()]))
    monkeypatch.setattr(setup_cli, "_run", lambda *args: (1, "token=secret"))
    assert setup_cli.main(["doctor"]) == 1
    output = capsys.readouterr().out
    assert "credentials missing" in output
    assert "codex login" in output
    assert "secret" not in output


def test_new_adapter_refuses_existing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src/adk_harness/coding/adapters").mkdir(parents=True)
    (tmp_path / "src/adk_harness/coding/adapters/existing.py").write_text("x")
    assert setup_cli.main(["new-adapter", "existing"]) == 2


def test_new_adapter_rejects_invalid_names(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    for name in ("Class", "class", "has-dash", "écho"):
        assert setup_cli.main(["new-adapter", name]) == 2


def test_new_adapter_rejects_symlinked_ancestor(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "src").symlink_to(outside, target_is_directory=True)
    assert setup_cli.main(["new-adapter", "escape"]) == 2
    assert not (outside / "adk_harness").exists()


def test_new_adapter_generates_runnable_check(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src/adk_harness/coding/adapters").mkdir(parents=True)
    (tmp_path / "src/adk_harness/__init__.py").write_text("")
    (tmp_path / "src/adk_harness/coding/adapters/__init__.py").write_text("")
    shutil.copyfile(
        Path(__file__).parents[2] / "src/adk_harness/coding/protocol.py",
        tmp_path / "src/adk_harness/coding/protocol.py",
    )
    assert setup_cli.main(["new-adapter", "offline_echo"]) == 0
    env = {**os.environ, "PYTHONPATH": str(tmp_path / "src")}
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/coding/adapters/test_offline_echo.py", "-q"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_install_plugin_preserves_previous_copy_as_backup(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "plugin.json").write_text("{}")
    (source / "mcp_config.json").write_text(
        '{"mcpServers":{"adk-harness":{"command":"old","env":{"ADK_PRECEDENTS":"old"}}}}'
    )
    target = tmp_path / "installed"
    target.mkdir()
    (target / "old.txt").write_text("keep")
    monkeypatch.setattr(setup_cli, "_plugin_source", lambda: source)
    monkeypatch.setattr(setup_cli, "PLUGIN_DIR", target)
    assert setup_cli._install_plugin()[0] is True
    assert (target.with_name("installed.backup") / "old.txt").read_text() == "keep"
    data = json.loads((target / "mcp_config.json").read_text())
    assert data["mcpServers"]["adk-harness"]["env"].get("ADK_PRECEDENTS") is None

    rollback_target = tmp_path / "rollback"
    rollback_target.mkdir()
    (rollback_target / "old.txt").write_text("keep")
    monkeypatch.setattr(setup_cli, "PLUGIN_DIR", rollback_target)
    original_rename = Path.rename

    def fail_final_rename(path, destination):
        if path.name.startswith(".rollback-"):
            raise OSError("simulated replacement failure")
        return original_rename(path, destination)

    monkeypatch.setattr(Path, "rename", fail_final_rename)
    assert setup_cli._install_plugin()[0] is False
    assert (rollback_target / "old.txt").read_text() == "keep"
    assert not rollback_target.with_name("rollback.backup").exists()


def test_install_plugin_refuses_existing_backup(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "plugin.json").write_text("{}")
    target = tmp_path / "installed"
    (target.with_name("installed.backup")).mkdir()
    monkeypatch.setattr(setup_cli, "_plugin_source", lambda: source)
    monkeypatch.setattr(setup_cli, "PLUGIN_DIR", target)
    ok, detail = setup_cli._install_plugin()
    assert not ok and "backup already exists" in detail
