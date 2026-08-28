from adk_harness.coding.protocol import HarnessSpec
from adk_harness.coding.registry import default_registry


def test_entrypoint_failure_isolated(monkeypatch) -> None:
    class Broken:
        name = "broken"

        def load(self):
            raise ImportError("optional package missing")

    monkeypatch.setattr(
        "importlib.metadata.entry_points", lambda **kwargs: [Broken()]
    )
    registry = default_registry(include_antigravity=False)
    assert registry.get("broken").spec.available is False


def test_valid_and_malformed_entrypoints_and_builtin_collision(monkeypatch) -> None:
    class Valid:
        spec = HarnessSpec(id="plugin", version="1", available=True)

        async def discover(self):
            return self.spec

        def run(self, prompt, *, cwd, session_id=None):
            raise NotImplementedError

        async def aclose(self):
            return None

    class Entry:
        def __init__(self, name, value):
            self.name, self.value = name, value

        def load(self):
            return self.value

    monkeypatch.setattr(
        "importlib.metadata.entry_points",
        lambda **kwargs: [
            Entry("plugin", Valid),
            Entry("malformed", object),
            Entry("codex", Valid),
        ],
    )
    registry = default_registry(include_antigravity=False)
    assert registry.get("plugin").spec.id == "plugin"
    assert registry.get("malformed").spec.available is False
    assert registry.get("codex").__class__.__name__ == "CodexHarness"
