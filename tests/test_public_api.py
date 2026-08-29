import importlib

import adk_harness


def test_public_api_exposes_governed_workspace_and_workflow_models() -> None:
    assert adk_harness.TaskRequest
    assert adk_harness.ChangeSet
    assert adk_harness.Approval
    assert adk_harness.ActivityEvent
    assert adk_harness.AntigravityIntegration


def test_retired_generic_architecture_is_not_importable() -> None:
    for module in ("adk_harness.coding", "adk_harness.mcp", "adk_harness.mcp_server"):
        try:
            importlib.import_module(module)
        except ModuleNotFoundError:
            continue
        raise AssertionError(f"retired module remains importable: {module}")
