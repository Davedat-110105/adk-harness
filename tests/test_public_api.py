"""Canonical exports and compatibility surfaces."""

import warnings
from importlib import import_module

import adk_harness
from adk_harness import content_armor, precedent_stores, workspace


def test_canonical_public_exports() -> None:
    assert adk_harness.MatchResult is not None
    assert adk_harness.WorkspaceApp is workspace.WorkspaceApp
    assert adk_harness.build_workspace_app is workspace.build_workspace_app
    assert adk_harness.ContentArmor is content_armor.ContentArmor
    assert adk_harness.SQLitePrecedentStore is precedent_stores.SQLitePrecedentStore


def test_legacy_modules_share_canonical_runtime_state() -> None:
    for legacy, canonical in {
        "protocol": "coding.protocol",
        "registry": "coding.registry",
        "harness_agent": "coding.harness_agent",
        "adapters.codex": "coding.adapters.codex",
        "adapters.opencode": "coding.adapters.opencode",
        "precedent_stores": "governance.stores",
        "mcp_server": "mcp.server",
        "setup_cli": "cli.main",
    }.items():
        assert import_module(f"adk_harness.{legacy}") is import_module(f"adk_harness.{canonical}")


def test_legacy_modules_and_names_remain_available() -> None:
    from adk_harness import armor, stores

    assert armor.ContentArmor is content_armor.ContentArmor
    assert stores.SQLitePrecedentStore is precedent_stores.SQLitePrecedentStore
    assert workspace.WorkspaceFleet is workspace.WorkspaceApp


def test_legacy_store_name_warns_and_preserves_identity() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        legacy = precedent_stores.PersistentPrecedentStore

    assert legacy is precedent_stores.SQLitePrecedentStore
    assert any(item.category is DeprecationWarning for item in caught)


def test_base_import_does_not_require_workspace_extra() -> None:
    import subprocess
    import sys

    script = """import builtins
original = builtins.__import__
def without_google_client(name, *args, **kwargs):
    if name.startswith("googleapiclient"):
        raise ImportError("Workspace extra absent")
    return original(name, *args, **kwargs)
builtins.__import__ = without_google_client
import adk_harness
assert adk_harness.WorkspaceApp
assert adk_harness.HarnessAgent
"""
    subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True)
