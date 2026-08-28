"""Import aliases for the former flat layout; all state stays in feature modules."""

import sys

from .coding import adapters, fleet, harness_agent, protocol, registry
from .coding.adapters import antigravity, claude_code, codex, opencode
from .governance import content_armor, ledger, precedents, stores

for _name, _module in {
    "protocol": protocol,
    "registry": registry,
    "fleet": fleet,
    "agent": harness_agent,
    "harness_agent": harness_agent,
    "precedent": precedents,
    "ledger": ledger,
    "content_armor": content_armor,
    "precedent_stores": stores,
    "adapters": adapters,
    "adapters.antigravity": antigravity,
    "adapters.claude_code": claude_code,
    "adapters.codex": codex,
    "adapters.opencode": opencode,
}.items():
    sys.modules[f"adk_harness.{_name}"] = _module
    if "." not in _name:
        setattr(sys.modules["adk_harness"], _name, _module)
