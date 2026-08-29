"""Governance aliases retained for import stability during migration."""

import sys

from .governance import content_armor, ledger, precedents, stores

for _name, _module in {
    "precedent": precedents,
    "ledger": ledger,
    "content_armor": content_armor,
    "precedent_stores": stores,
}.items():
    sys.modules[f"adk_harness.{_name}"] = _module
    if "." not in _name:
        setattr(sys.modules["adk_harness"], _name, _module)
