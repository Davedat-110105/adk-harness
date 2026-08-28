"""Exercise demo policies without importing their eager, live agent setup."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from coactra import Decision, DecisionOutcome, PolicyRequest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "file,class_name",
    [
        ("examples/agents/local/agent.py", "LocalPolicy"),
        ("examples/agents/fleet/agent.py", "WorkspacePolicy"),
        ("examples/scripts/multi_adapter_fleet.py", "LocalRepoPolicy"),
        ("examples/scripts/run_fleet_on_repository.py", "RepoPolicy"),
    ],
)
async def test_example_policy_rejects_siblings_traversal_and_symlink_escape(
    file: str,
    class_name: str,
    tmp_path: Path,
) -> None:
    tree = ast.parse((ROOT / file).read_text())
    namespace: dict[str, Any] = {
        "Path": Path,
        "Decision": Decision,
        "DecisionOutcome": DecisionOutcome,
        "PolicyRequest": PolicyRequest,
        "Any": Any,
    }
    nodes: list[ast.stmt] = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name):
                    namespace[target.id] = value
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            nodes.append(node)
        if isinstance(node, ast.FunctionDef) and node.name in {"_words", "_requested"}:
            nodes.append(node)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), file, "exec"), namespace)
    root = tmp_path / "repo"
    child, sibling = root / "child", tmp_path / "repo2"
    child.mkdir(parents=True)
    sibling.mkdir()
    (root / "escape").symlink_to(sibling, target_is_directory=True)
    policy = namespace[class_name](root)
    for path, expected in [
        (root, DecisionOutcome.allow),
        (child, DecisionOutcome.allow),
        (sibling, DecisionOutcome.deny),
        (root / "../repo2", DecisionOutcome.deny),
        (root / "escape", DecisionOutcome.deny),
    ]:
        request = SimpleNamespace(
            resource="tool:run_demo",
            context={"cwd": str(path), "tool_args": {"instruction": "inspect"}},
        )
        assert (await policy.check(request)).outcome is expected


@pytest.mark.asyncio
async def test_cookbook_adapters_stream_offline(tmp_path: Path) -> None:
    blocks = re.findall(r"```python\n(.*?)\n```", (ROOT / "examples/README.md").read_text(), re.S)
    classes = ("EchoHarness", "SubprocessEchoHarness")
    assert len(blocks) == len(classes)
    for block, name in zip(blocks, classes, strict=True):
        namespace: dict[str, Any] = {}
        exec(compile(block, "examples/README.md", "exec"), namespace)
        harness = namespace[name]()
        assert (await harness.discover()).available
        turns = [turn async for turn in harness.run("hello", cwd=str(tmp_path))]
        assert turns[0].text == "hello"
        await harness.aclose()
