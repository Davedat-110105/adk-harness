"""Harness discovery and lookup.

This is the Agent Registry: what is installed, at what version, and what it can
do. It imports nothing vendor-specific and nothing from ADK, which is what lets
the SDK install and run with only a subset of the harnesses present.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable

from adk_harness.protocol import Harness, HarnessSpec

__all__ = ["HarnessRegistry"]


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
