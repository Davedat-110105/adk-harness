from pathlib import Path


def test_supported_workspace_example_is_present() -> None:
    assert Path("examples/agents/workspace/agent.py").exists()
