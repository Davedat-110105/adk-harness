"""Durable stores for the governance precedent loop.

The matcher stays in :mod:`adk_harness.governance.precedents`; this module only gives it a
SQLite-backed lifetime so a process restart does not erase human decisions.
"""

from __future__ import annotations

import json
import sqlite3
import warnings
from collections.abc import Iterable, Mapping
from datetime import datetime
from os import PathLike
from typing import TYPE_CHECKING, Any, Self

from .precedents import Applicability, Precedent, PrecedentStore

__all__ = ["PersistentPrecedentStore", "SQLitePrecedentStore"]

_VALUE_TYPE = "__adk_harness_value_type__"


class SQLitePrecedentStore(PrecedentStore):
    """Keep precedents in SQLite while reusing the frozen matcher unchanged."""

    def __init__(
        self,
        database: str | PathLike[str],
        precedents: Iterable[Precedent] = (),
    ) -> None:
        self._connection = sqlite3.connect(database)
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS precedents (
                precedent_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            )
            """
        )
        self._connection.commit()

        self._by_id: dict[str, Precedent] = {}
        for payload, in self._connection.execute(
            "SELECT payload FROM precedents ORDER BY rowid"
        ):
            PrecedentStore.add(self, _from_payload(payload))
        for precedent in precedents:
            self.add(precedent)

    def add(self, precedent: Precedent) -> None:
        """Persist a decision and any precedent it retires in one transaction."""
        retired_id = precedent.supersedes
        PrecedentStore.add(self, precedent)

        to_persist = [precedent]
        if retired_id is not None and retired_id in self._by_id:
            to_persist.append(self._by_id[retired_id])
        with self._connection:
            self._connection.executemany(
                """
                INSERT INTO precedents (precedent_id, payload)
                VALUES (?, ?)
                ON CONFLICT(precedent_id) DO UPDATE SET payload=excluded.payload
                """,
                ((_precedent.precedent_id, _to_payload(_precedent)) for _precedent in to_persist),
            )

    def close(self) -> None:
        """Close the database connection so callers can release the file cleanly."""
        self._connection.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


if TYPE_CHECKING:
    PersistentPrecedentStore = SQLitePrecedentStore


def __getattr__(name: str) -> Any:
    if name == "PersistentPrecedentStore":
        warnings.warn(
            "PersistentPrecedentStore is deprecated; use SQLitePrecedentStore",
            DeprecationWarning,
            stacklevel=2,
        )
        return SQLitePrecedentStore
    raise AttributeError(name)


def _to_payload(precedent: Precedent) -> str:
    return json.dumps(
        {
            "precedent_id": precedent.precedent_id,
            "action": precedent.action,
            "ambiguity_type": precedent.ambiguity_type,
            "applicability": [
                {
                    "field": predicate.field,
                    "operator": predicate.operator,
                    "value": _encode_value(predicate.value),
                }
                for predicate in precedent.applicability
            ],
            "decision": _encode_value(dict(precedent.decision)),
            "rationale": precedent.rationale,
            "confirmed_by": precedent.confirmed_by,
            "created_at": precedent.created_at.isoformat(),
            "review_after": (
                precedent.review_after.isoformat()
                if precedent.review_after is not None
                else None
            ),
            "supersedes": precedent.supersedes,
            "status": precedent.status,
            "schema_version": precedent.schema_version,
        },
        sort_keys=True,
    )


def _from_payload(payload: str) -> Precedent:
    data = json.loads(payload)
    return Precedent(
        precedent_id=data["precedent_id"],
        action=data["action"],
        ambiguity_type=data["ambiguity_type"],
        applicability=tuple(
            Applicability(
                field=item["field"],
                operator=item["operator"],
                value=_decode_value(item["value"]),
            )
            for item in data["applicability"]
        ),
        decision=_decode_value(data["decision"]),
        rationale=data["rationale"],
        confirmed_by=data["confirmed_by"],
        created_at=datetime.fromisoformat(data["created_at"]),
        review_after=(
            datetime.fromisoformat(data["review_after"])
            if data["review_after"] is not None
            else None
        ),
        supersedes=data["supersedes"],
        status=data["status"],
        schema_version=data["schema_version"],
    )


def _encode_value(value: Any) -> Any:
    if isinstance(value, tuple):
        return {_VALUE_TYPE: "tuple", "items": [_encode_value(item) for item in value]}
    if isinstance(value, list):
        return [_encode_value(item) for item in value]
    if isinstance(value, Mapping):
        return {
            _VALUE_TYPE: "mapping",
            "items": [
                [_encode_value(key), _encode_value(item)]
                for key, item in value.items()
            ],
        }
    return value


def _decode_value(value: Any) -> Any:
    if isinstance(value, list):
        return [_decode_value(item) for item in value]
    if isinstance(value, dict) and value.get(_VALUE_TYPE) == "tuple":
        return tuple(_decode_value(item) for item in value["items"])
    if isinstance(value, dict) and value.get(_VALUE_TYPE) == "mapping":
        return {
            _decode_value(key): _decode_value(item)
            for key, item in value["items"]
        }
    if isinstance(value, dict):
        return {key: _decode_value(item) for key, item in value.items()}
    return value
