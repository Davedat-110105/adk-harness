"""Publish what a machine can do, and read back what it has done.

Two questions an organisation asks about a fleet of agents. What is out there,
and what happened. Both answers live in the same Firestore project, so a
developer on another machine sees the same catalogue and the same history.

Nothing here decides anything. Publishing a capability does not grant it, and
reading a decision does not change it.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

__all__ = ["AgentCatalogue", "CatalogueEntry", "MemoryBank", "Recollection"]

CATALOGUE_COLLECTION = "agent_catalogue"
LEDGER_COLLECTION = "action_ledger"


@dataclass(frozen=True, slots=True)
class CatalogueEntry:
    """One machine's published capability, as another machine sees it."""

    agent_id: str
    subject: str
    services: tuple[str, ...]
    operations: tuple[str, ...]
    granted_scopes: tuple[str, ...]
    policy_version: str
    version: str
    published_at: datetime

    def summary(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "subject": self.subject,
            "services": list(self.services),
            "operations": list(self.operations),
            "granted_scopes": list(self.granted_scopes),
            "policy_version": self.policy_version,
            "version": self.version,
            "published_at": self.published_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class Recollection:
    """One decision this fleet made, recalled from a previous session."""

    operation: str
    outcome: str
    actor: str
    change_hash: str
    recorded_at: datetime
    reason: str = ""

    def summary(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "outcome": self.outcome,
            "actor": self.actor,
            "change_hash": self.change_hash,
            "recorded_at": self.recorded_at.isoformat(),
            "reason": self.reason,
        }


class AgentCatalogue:
    """Publish and discover the agents an organisation has approved."""

    def __init__(self, client: Any, *, agent_version: str = "0.1.0") -> None:
        self._client = client
        self._agent_version = agent_version

    def publish(
        self,
        *,
        agent_id: str,
        subject: str,
        operations: Sequence[str],
        granted_scopes: Sequence[str],
        policy_version: str,
    ) -> CatalogueEntry:
        """Record what this machine can do, replacing its previous entry."""
        services = tuple(sorted({name.split("_", 1)[0] for name in operations}))
        entry = CatalogueEntry(
            agent_id=agent_id,
            subject=subject,
            services=services,
            operations=tuple(sorted(operations)),
            granted_scopes=tuple(sorted(granted_scopes)),
            policy_version=policy_version,
            version=self._agent_version,
            published_at=datetime.now(UTC),
        )
        self._client.collection(CATALOGUE_COLLECTION).document(agent_id).set(entry.summary())
        return entry

    def discover(self, *, service: str | None = None) -> tuple[dict[str, Any], ...]:
        """List the agents published to this project, newest first."""
        found = [
            document.to_dict() or {}
            for document in self._client.collection(CATALOGUE_COLLECTION).stream()
        ]
        if service is not None:
            found = [item for item in found if service in (item.get("services") or ())]
        return tuple(sorted(found, key=lambda item: str(item.get("published_at")), reverse=True))


class MemoryBank:
    """Read back what the fleet decided, across sessions and machines."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def recall(
        self, *, since_days: int = 30, actor: str | None = None, limit: int = 50
    ) -> tuple[Recollection, ...]:
        """Return past decisions, newest first.

        The ledger is append-only, so this is a read of what happened rather
        than a cache that can drift from it.
        """
        cutoff = datetime.now(UTC) - timedelta(days=since_days)
        recalled: list[Recollection] = []
        for document in self._client.collection(LEDGER_COLLECTION).stream():
            entry = document.to_dict() or {}
            recorded = entry.get("recorded_at")
            if not isinstance(recorded, datetime):
                continue
            if recorded < cutoff:
                continue
            if actor is not None and entry.get("actor") != actor:
                continue
            recalled.append(
                Recollection(
                    operation=str(entry.get("action", "")),
                    outcome=str(entry.get("policy_outcome", "")),
                    actor=str(entry.get("actor", "")),
                    change_hash=str(entry.get("input_hash", "")),
                    recorded_at=recorded,
                    reason=str(entry.get("policy_reason") or ""),
                )
            )
        recalled.sort(key=lambda item: item.recorded_at, reverse=True)
        return tuple(recalled[:limit])


def agent_id(subject: str) -> str:
    """Name this machine in the catalogue, stably and without a hostname."""
    import hashlib
    import platform

    seed = f"{subject}:{platform.node()}"
    return "agent-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def firestore_client(project_id: str | None = None) -> Any | None:
    """Open the shared project, or return nothing when none is configured."""
    target = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not target:
        return None
    try:
        from google.cloud import firestore

        return firestore.Client(project=target)
    except Exception:
        return None
