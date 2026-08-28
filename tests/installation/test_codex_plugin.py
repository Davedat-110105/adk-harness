import json
from pathlib import Path

ROOT = Path(__file__).parents[2]
PLUGIN = ROOT / "plugins" / "adk-harness"


def test_codex_plugin_manifest_and_marketplace_are_consistent() -> None:
    manifest = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text())
    marketplace = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text())
    entry = marketplace["plugins"][0]

    assert manifest["name"] == entry["name"] == PLUGIN.name
    assert entry["source"]["path"] == "./plugins/adk-harness"
    assert manifest["mcpServers"] == "./.mcp.json"
    assert manifest["skills"] == "./skills/"


def test_mcp_server_runs_from_workspace_and_uses_pinned_source() -> None:
    config = json.loads((PLUGIN / ".mcp.json").read_text())["mcpServers"]["adk-harness"]

    assert config["cwd"] == "."
    assert config["command"] == "uvx"
    assert config["args"][-2:] == ["adk-harness", "serve"]
    source = config["args"][config["args"].index("--from") + 1]
    assert "git+https://github.com/Davedat-110105/adk-harness.git@" in source
    assert len(source.rsplit("@", 1)[1]) == 40
    assert {
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GOOGLE_CLOUD_PROJECT",
        "ADK_SERVICES",
        "ADK_TOOLS",
        "ADK_LEDGER",
        "ADK_HARNESSES",
        "ADK_ALLOWED_DOMAINS",
    } <= set(config["env_vars"])
