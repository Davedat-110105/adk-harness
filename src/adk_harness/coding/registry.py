"""Harness discovery and lookup.

This is the Agent Registry: what is installed, at what version, and what it can
do. It imports nothing vendor-specific and nothing from ADK, which is what lets
the SDK install and run with only a subset of the harnesses present.
"""

from __future__ import annotations

import asyncio
import importlib.metadata
from collections.abc import Iterable
from typing import Any

from adk_harness.coding.protocol import Harness, HarnessSpec

__all__ = ["HarnessRegistry", "default_registry"]


class _UnavailableHarness:
    """Keep a broken optional extension visible without breaking discovery."""

    def __init__(self, harness_id: str, detail: str) -> None:
        self.spec = HarnessSpec(id=harness_id, version="unknown", detail=detail)

    async def discover(self) -> HarnessSpec:
        return self.spec

    def run(self, prompt: str, *, cwd: str, session_id: str | None = None) -> Any:
        raise RuntimeError(self.spec.detail or "harness unavailable")

    async def aclose(self) -> None:
        return None


class HarnessRegistry:
    """Hold harnesses, resolve which are actually usable here."""

    def __init__(self, harnesses: Iterable[Harness] = ()) -> None:
        self._harnesses: dict[str, Harness] = {}
        self._specs: dict[str, HarnessSpec] = {}
        for harness in harnesses:
            self.register(harness)

    def register(self, harness: Harness) -> None:
        self._harnesses[harness.spec.id] = harness
        self._specs[harness.spec.id] = harness.spec

    async def discover_all(self) -> tuple[HarnessSpec, ...]:
        """Probe every harness concurrently.

        A harness that raises during discovery is recorded as unavailable with
        the error in `detail`, never propagated. One broken adapter must not
        take down a fleet that has other working ones.
        """
        ids = tuple(self._harnesses)
        results = await asyncio.gather(
            *(self._harnesses[i].discover() for i in ids),
            return_exceptions=True,
        )
        for harness_id, result in zip(ids, results, strict=True):
            if isinstance(result, BaseException):
                previous = self._specs[harness_id]
                self._specs[harness_id] = HarnessSpec(
                    id=harness_id,
                    version=previous.version,
                    capabilities=previous.capabilities,
                    available=False,
                    detail=f"{type(result).__name__}: {result}",
                )
            else:
                self._specs[harness_id] = result
                # Adapters normally update ``self.spec`` themselves. Keep the
                # object consumed by fleet wiring in sync for simple custom
                # adapters that only return the discovered spec.
                try:
                    self._harnesses[harness_id].spec = result
                except (AttributeError, TypeError):
                    pass
        return self.specs()

    def specs(self) -> tuple[HarnessSpec, ...]:
        return tuple(self._specs[i] for i in sorted(self._specs))

    def available(self) -> tuple[Harness, ...]:
        return tuple(
            self._harnesses[i] for i in sorted(self._specs) if self._specs[i].available
        )

    def by_capability(self, capability: str) -> tuple[Harness, ...]:
        return tuple(
            self._harnesses[i]
            for i in sorted(self._specs)
            if self._specs[i].available and capability in self._specs[i].capabilities
        )

    def get(self, harness_id: str) -> Harness:
        try:
            return self._harnesses[harness_id]
        except KeyError:
            known = ", ".join(sorted(self._harnesses)) or "none"
            raise KeyError(
                f"no harness registered as {harness_id!r}; registered: {known}"
            ) from None

    def __len__(self) -> int:
        return len(self._harnesses)


def default_registry(*, include_antigravity: bool = True) -> HarnessRegistry:
    """Build the standard registry, including optional third party plugins.

    Imports are deliberately local: a base install remains usable without any
    vendor SDKs. Entry point failures become unavailable specs instead of
    taking down the working adapters.
    """
    factories: dict[str, Any] = {}
    from adk_harness.coding.adapters import ClaudeCodeHarness, CodexHarness, OpenCodeHarness

    factories.update(
        codex=CodexHarness,
        claude_code=ClaudeCodeHarness,
        opencode=OpenCodeHarness,
    )
    if include_antigravity:
        from adk_harness.coding.adapters import AntigravityHarness

        factories["antigravity"] = AntigravityHarness

    harnesses: list[Harness] = [factory() for factory in factories.values()]
    entry_points = importlib.metadata.entry_points(group="adk_harness.coding.adapters")
    for entry_point in sorted(entry_points, key=lambda item: item.name):
        try:
            loaded = entry_point.load()
            harness: Any = loaded() if callable(loaded) else loaded
            spec = getattr(harness, "spec", None)
            if not isinstance(spec, HarnessSpec) or not isinstance(spec.id, str) or not spec.id:
                raise TypeError("entry point must provide a Harness with a valid HarnessSpec")
            if not all(
                callable(getattr(harness, name, None))
                for name in ("discover", "run", "aclose")
            ):
                raise TypeError("entry point does not implement the Harness protocol")
            harness_id = spec.id
            if harness_id not in factories:
                harnesses.append(harness)
                factories[harness_id] = loaded
        except Exception as exc:  # extensions are explicitly third party
            harness_id = entry_point.name
            if harness_id not in factories:
                harnesses.append(_UnavailableHarness(harness_id, f"extension unavailable: {exc}"))
                factories[harness_id] = None
    return HarnessRegistry(harnesses)
