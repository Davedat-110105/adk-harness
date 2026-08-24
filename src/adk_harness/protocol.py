"""The adapter contract. Every harness implements exactly this.

This module imports nothing vendor-specific, and nothing from ADK. It is the
one file every adapter and every consumer agrees on, so it stays small and it
stays frozen.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

__all__ = ["HarnessSpec", "HarnessTurn", "Harness"]


@dataclass(frozen=True, slots=True)
class HarnessSpec:
    """Static description of one harness.

    `available` is False when the harness is not installed or not reachable on
    this machine. Adapters report that instead of raising, so a fleet can run
    with whatever subset is present.
    """

    id: str
    version: str
    capabilities: tuple[str, ...] = ()
    available: bool = False
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class HarnessTurn:
    """One streamed step out of a harness, normalized across vendors.

    `raw` carries the vendor payload untouched. The core never branches on its
    shape; it exists so callers that care about a specific harness can reach
    through without the protocol growing vendor fields.
    """

    kind: str
    text: str | None = None
    tool_name: str | None = None
    tool_args: dict[str, Any] = field(default_factory=dict)
    raw: Any = None

    KINDS = ("text", "tool_call", "tool_result", "usage", "error")


@runtime_checkable
class Harness(Protocol):
    """A coding-agent harness, presented uniformly.

    An adapter never decides whether an action is permitted. It streams turns;
    the governance plugin decides. Adapters import their vendor SDK inside
    `discover`, never at module import time, so a missing harness degrades to
    `available=False` rather than an ImportError at import.
    """

    spec: HarnessSpec

    async def discover(self) -> HarnessSpec:
        """Resolve version and availability. Must not raise if absent."""
        ...

    def run(
        self,
        prompt: str,
        *,
        cwd: str,
        session_id: str | None = None,
    ) -> AsyncIterator[HarnessTurn]:
        """Stream the harness working. Never buffers a whole session."""
        ...

    async def aclose(self) -> None:
        """Release subprocesses, sockets, and clients."""
        ...
