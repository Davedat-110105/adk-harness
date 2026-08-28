"""Compatibility entry point for :mod:`adk_harness.mcp.server`."""

import sys
from importlib import import_module

_canonical = import_module("adk_harness.mcp.server")

if __name__ == "__main__":
    raise SystemExit(_canonical.main())
else:
    sys.modules[__name__] = _canonical
