"""Compatibility module for :mod:`adk_harness.governance.stores`."""

import warnings
from typing import TYPE_CHECKING

from .governance.stores import SQLitePrecedentStore

if TYPE_CHECKING:
    PersistentPrecedentStore = SQLitePrecedentStore


def __getattr__(name: str):
    if name == "PersistentPrecedentStore":
        warnings.warn(
            "PersistentPrecedentStore is deprecated; use SQLitePrecedentStore",
            DeprecationWarning,
            stacklevel=2,
        )
        return SQLitePrecedentStore
    raise AttributeError(name)

__all__ = ["PersistentPrecedentStore", "SQLitePrecedentStore"]
