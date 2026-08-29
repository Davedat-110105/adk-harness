import importlib
import json

from adk_harness.cli.main import main


def test_cli_exposes_auth_commands_without_approval_bypass(monkeypatch, capsys) -> None:
    cli_module = importlib.import_module("adk_harness.cli.main")
    monkeypatch.setattr(cli_module, "_auth_status", lambda purpose: {"stored": False})
    assert main(["status"]) == 0
    output = capsys.readouterr().out
    assert "stored: False" in output
    assert "approved" not in output.lower()


def test_cli_rejects_model_facing_approval_flag() -> None:
    try:
        main(["--approved"])
    except SystemExit as exc:
        assert exc.code != 0
    else:
        raise AssertionError("--approved must not be a supported entrypoint")


def test_status_accepts_explicit_client_config_and_subject_without_environment(
    monkeypatch, capsys, tmp_path
) -> None:
    config = tmp_path / "client.json"
    config.write_text(json.dumps({"installed": {"client_id": "client-id"}}), encoding="utf-8")
    cli_module = importlib.import_module("adk_harness.cli.main")
    seen: list[tuple[object, str | None, str | None]] = []

    def status(purpose, *, client_config=None, subject=None):
        seen.append((purpose, client_config, subject))
        return {"stored": False, "authenticated": False}

    monkeypatch.delenv("ADK_HARNESS_GOOGLE_CLIENT_CONFIG", raising=False)
    monkeypatch.setattr(cli_module, "_auth_status", status)
    assert (
        main(["status", "--client-config", str(config), "--subject", "google-sub-1"])
        == 0
    )
    capsys.readouterr()
    assert len(seen) == 2
    assert all(path == str(config) and subject == "google-sub-1" for _, path, subject in seen)


def test_cli_rejects_retired_commands() -> None:
    try:
        main(["serve"])
    except SystemExit as exc:
        assert exc.code != 0
    else:
        raise AssertionError("serve must not be a supported entrypoint")


def test_install_plugin_copies_packaged_assets(tmp_path, capsys) -> None:
    destination = tmp_path / "plugins" / "adk-harness"
    config = tmp_path / "mcp_config.json"
    assert (
        main(
            [
                "install-plugin",
                "--plugin-dir",
                str(destination),
                "--mcp-config",
                str(config),
            ]
        )
        == 0
    )
    assert (destination / "plugin.json").is_file()
    assert (destination / "skills" / "governed-workspace" / "SKILL.md").is_file()
    assert (destination / "rules" / "governance.md").is_file()
    assert str(destination) in capsys.readouterr().out


def test_install_plugin_replaces_an_existing_installation(tmp_path) -> None:
    destination = tmp_path / "adk-harness"
    destination.mkdir()
    stale = destination / "mcp_config.json"
    stale.write_text("{}", encoding="utf-8")
    config = tmp_path / "mcp_config.json"
    assert (
        main(
            ["install-plugin", "--plugin-dir", str(destination), "--mcp-config", str(config)]
        )
        == 0
    )
    assert not stale.exists()
    assert (destination / "plugin.json").is_file()


def test_install_plugin_registers_the_server_without_losing_others(tmp_path) -> None:
    """Antigravity reads one shared file, so other people's servers must survive."""
    config = tmp_path / "mcp_config.json"
    config.write_text(
        json.dumps({"mcpServers": {"someone-else": {"command": "/bin/true"}}}),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "install-plugin",
                "--plugin-dir",
                str(tmp_path / "plugin"),
                "--mcp-config",
                str(config),
            ]
        )
        == 0
    )

    servers = json.loads(config.read_text(encoding="utf-8"))["mcpServers"]
    assert servers["someone-else"] == {"command": "/bin/true"}
    assert servers["adk-harness"]["args"] == ["-m", "adk_harness", "mcp"]


def test_install_plugin_creates_the_config_when_absent(tmp_path) -> None:
    config = tmp_path / "nested" / "mcp_config.json"

    assert (
        main(
            [
                "install-plugin",
                "--plugin-dir",
                str(tmp_path / "plugin"),
                "--mcp-config",
                str(config),
            ]
        )
        == 0
    )

    assert "adk-harness" in json.loads(config.read_text(encoding="utf-8"))["mcpServers"]
